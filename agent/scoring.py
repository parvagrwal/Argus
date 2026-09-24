"""Deterministic fraud_probability + pattern classifier from graph query outputs. No LLM here."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

from agent.schema import Pattern

# Policy thresholds (bank_policy.md). The action threshold is R1's 0.70; cold starts stay below it.
R1_VERIFY_FIRST = 0.70
COLD_START_CAP = 0.69
MIN_INDEPENDENT_EVIDENCE = 2


def attrs(v: dict[str, Any]) -> dict[str, Any]:
    """Flatten a TigerGraph vertex print ({"attributes": {"Alias.@acc": ..}}) to plain keys."""
    out: dict[str, Any] = dict(v.get("attributes", v))
    return {k.split(".")[-1].lstrip("@"): val for k, val in out.items()}


def merge_blocks(result: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a REST++ `results` list of PRINT blocks into one dict."""
    merged: dict[str, Any] = {}
    for block in (result or {}).get("results", []) or []:
        if isinstance(block, dict):
            merged.update(block)
    return merged


@dataclass
class Features:
    """Every field is a signal a judge can recompute from the named query output."""

    risk_score: float = 0.0            # flagged txn model score (input, never a verdict)
    customer_report: float = 0.0       # trigger_type == customer_report (dispute)
    online: float = 0.0                # flagged txn channel online
    new_device: float = 0.0            # id_15 == New on the flagged txn (pattern 3)
    proxy: float = 0.0                 # id_23 proxy flag on the flagged txn
    micro_auth_burst: float = 0.0      # velocity_check: >=3 small online auths in an hour (R5)
    testing_then_purchase: float = 0.0 # velocity_check: burst followed by a larger purchase
    online_burst_48h: float = 0.0      # card_window: >=2 online txns within 48h of the flag (pattern 2)
    amount_ratio_log: float = 0.0      # log(flagged amount / median window amount), clipped
    out_of_region: float = 0.0         # in-person flag in a region with no baseline history (pattern 4)
    region_history: float = 0.0        # exonerating: card has baseline history in the flagged region
    trip_pattern: float = 0.0          # exonerating: >=3 distinct days in the flagged region while home continued
    mixed_channel: float = 0.0         # online + in-person inside the window (pattern 5)
    prior_fraud_log: float = 0.0       # log1p(confirmed-fraud closed cases on this card)
    prior_cleared: float = 0.0         # cleared closed cases on this card (>=1)
    shared_device_cards_log: float = 0.0  # log1p(other cards on the same non-hub device)
    neighbor_prior_fraud: float = 0.0  # a connected card has confirmed fraud (R6)
    ring: float = 0.0                  # component >=3 cards with >=2 carrying confirmed fraud (R9)
    structuring: float = 0.0           # >=3 online txns 400-500 within 40 min (undocumented typology 2)
    customer_denied: float = 0.0       # simulated evidence response
    customer_confirmed: float = 0.0    # simulated evidence response (exonerating)
    cold_start: float = 0.0            # no priors and no identity record
    queries_seen: set[str] = field(default_factory=set)
    flagged: dict[str, Any] = field(default_factory=dict)

    def vector(self) -> dict[str, float]:
        return {f.name: float(getattr(self, f.name)) for f in fields(self) if f.type == "float"}


# Priors chosen from the pattern definitions and the P0 closed-case counts; refit with fit_weights.
DEFAULT_WEIGHTS: dict[str, float] = {
    "risk_score": 1.2, "customer_report": 0.9, "online": 0.2, "new_device": 1.1, "proxy": 1.0,
    "micro_auth_burst": 1.4, "testing_then_purchase": 1.6, "online_burst_48h": 0.8, "amount_ratio_log": 0.5,
    "out_of_region": 1.3, "region_history": -1.6, "trip_pattern": -1.2, "mixed_channel": 0.7,
    "prior_fraud_log": 0.9, "prior_cleared": -0.4, "shared_device_cards_log": 0.8, "neighbor_prior_fraud": 1.3,
    "ring": 1.8, "structuring": 1.8, "customer_denied": 2.2, "customer_confirmed": -3.0, "cold_start": -0.3,
}
DEFAULT_BIAS = -1.6


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def score(feat: Features, weights: dict[str, float] | None = None, bias: float = DEFAULT_BIAS) -> dict[str, Any]:
    """Logistic score; returns the breakdown the InternalCaseRecord stores."""
    w = weights or DEFAULT_WEIGHTS
    vec = feat.vector()
    logit = bias + sum(w.get(k, 0.0) * v for k, v in vec.items())
    p = sigmoid(logit)
    capped = False
    if feat.cold_start and not (feat.customer_denied or feat.customer_confirmed) and p > COLD_START_CAP:
        p, capped = COLD_START_CAP, True
    return {"features": vec, "weights": {k: w.get(k, 0.0) for k in vec}, "bias": bias, "logit": logit,
            "probability": round(p, 4), "cold_start_capped": capped}


def fit_weights(rows: Iterable[tuple[Features, int]], l2: float = 0.05, iters: int = 2000, lr: float = 0.05) -> tuple[dict[str, float], float]:
    """L2-regularised logistic regression by gradient descent on (features, outcome) from closed cases.
    Outcome 1 = confirmed_fraud, 0 = cleared. Run on all 5,565 rows; store the result as DEFAULT_WEIGHTS."""
    data = [(f.vector(), int(y)) for f, y in rows]
    if not data:
        return dict(DEFAULT_WEIGHTS), DEFAULT_BIAS
    keys = list(data[0][0])
    w = {k: 0.0 for k in keys}
    b = 0.0
    n = len(data)
    for _ in range(iters):
        gw = {k: l2 * w[k] for k in keys}
        gb = 0.0
        for vec, y in data:
            err = sigmoid(b + sum(w[k] * vec[k] for k in keys)) - y
            gb += err
            for k in keys:
                gw[k] += err * vec[k]
        for k in keys:
            w[k] -= lr * gw[k] / n
        b -= lr * gb / n
    return w, b


def calibration_table(probs: list[float], outcomes: list[int], bins: int = 10) -> list[dict[str, float]]:
    """Reliability table (predicted vs observed rate per bin) so a judge can check calibration."""
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in zip(probs, outcomes) if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        if sel:
            out.append({"bin_lo": lo, "bin_hi": hi, "n": len(sel), "mean_pred": sum(p for p, _ in sel) / len(sel),
                        "observed": sum(y for _, y in sel) / len(sel)})
    return out


# ---------------------------------------------------------------- feature extraction per query


def _ts(s: str) -> float:
    from datetime import datetime
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").timestamp()


def apply_card_window(feat: Features, res: dict[str, Any], flagged_txn_id: str, opened_at: str) -> None:
    m = merge_blocks(res)
    feat.queries_seen.add("card_window")
    txns = [attrs(t) for t in m.get("transactions", [])]
    flagged = next((t for t in txns if str(t.get("txn_id")) == flagged_txn_id), None)
    if flagged:
        feat.flagged = flagged
        feat.risk_score = float(flagged.get("risk_score") or 0)
        feat.online = float(flagged.get("channel") == "online")
        feat.new_device = float(flagged.get("device_status") == "New")
        feat.proxy = float(bool(flagged.get("proxy_flag")))
        amts = sorted(float(t["amount"]) for t in txns if t.get("amount") is not None)
        if len(amts) >= 3:
            med = amts[len(amts) // 2] or 1.0
            feat.amount_ratio_log = max(-2.0, min(2.0, math.log(max(float(flagged["amount"]), 0.01) / med)))
        t0 = _ts(flagged["ts"])
        near = [t for t in txns if t.get("channel") == "online" and abs(_ts(t["ts"]) - t0) <= 48 * 3600]
        feat.online_burst_48h = float(len(near) >= 2)
        channels = {t.get("channel") for t in txns if abs(_ts(t["ts"]) - t0) <= 7 * 86400}
        feat.mixed_channel = float(len(channels) > 1)
    priors = [attrs(p) for p in m.get("prior_cases", [])]
    n_fraud = sum(p.get("outcome") == "confirmed_fraud" for p in priors)
    feat.prior_fraud_log = math.log1p(n_fraud)
    feat.prior_cleared = float(any(p.get("outcome") == "cleared" for p in priors))
    has_identity = bool(flagged and (flagged.get("device_status") or flagged.get("device_profile")))
    feat.cold_start = float(not priors and not has_identity)


def apply_velocity(feat: Features, res: dict[str, Any]) -> None:
    m = merge_blocks(res)
    feat.queries_seen.add("velocity_check")
    feat.micro_auth_burst = float(int(m.get("n_micro_auth_bursts", 0) or 0) > 0)
    feat.testing_then_purchase = float(bool(m.get("card_testing_sequence_detected")))
    rows = sorted((attrs(t) for t in m.get("transactions", [])), key=lambda t: t.get("ts", ""))
    online = [t for t in rows if t.get("channel") == "online" and 400 <= float(t.get("amount", 0)) < 500]
    for i, a in enumerate(online):
        if sum(1 for b in online[i:] if _ts(b["ts"]) - _ts(a["ts"]) <= 40 * 60) >= 3:
            feat.structuring = 1.0


def apply_device_neighbors(feat: Features, res: dict[str, Any]) -> None:
    m = merge_blocks(res)
    feat.queries_seen.add("device_neighbors")
    cards = [attrs(c) for c in m.get("connected_cards", [])]
    feat.shared_device_cards_log = math.log1p(len(cards))
    feat.neighbor_prior_fraud = float(any(c.get("prior_fraud_cases") for c in cards))
    if not feat.cold_start and m.get("n_devices", 0) == 0 and not feat.flagged.get("device_status"):
        feat.cold_start = float(feat.prior_fraud_log == 0 and not feat.prior_cleared)


def apply_ring(feat: Features, res: dict[str, Any]) -> None:
    m = merge_blocks(res)
    feat.queries_seen.add("detect_fraud_ring")
    size = int(m.get("component_size", 0) or 0)
    with_fraud = int(m.get("cards_with_prior_confirmed_fraud", 0) or 0)
    feat.ring = float(size >= 3 and with_fraud >= 2)


def apply_region(feat: Features, res: dict[str, Any]) -> None:
    m = merge_blocks(res)
    feat.queries_seen.add("region_profile")
    in_person = feat.flagged.get("channel") == "in_person"
    has_hist = bool(m.get("flagged_region_has_history"))
    feat.region_history = float(has_hist and in_person)  # pattern 4 is card-present; region history says nothing about an online txn
    home_cont = bool(m.get("home_activity_continued_in_window"))
    feat.out_of_region = float(in_person and not has_hist and not m.get("flagged_region_is_home") and int(m.get("baseline_txns", 0) or 0) > 0)
    feat.trip_pattern = float(in_person and int(m.get("distinct_window_days_in_flagged_region", 0) or 0) >= 3 and home_cont)


# ---------------------------------------------------------------- pattern classifier (R9 first)


def classify(feat: Features, prob: float, open_case_threshold: float = 0.30) -> tuple[str, str]:
    """Deterministic pattern label + factual basis (the LLM/narrator phrases the description)."""
    if prob < open_case_threshold or not feat.flagged:  # no graph row for the flagged txn: nothing to classify honestly
        return Pattern.none.value, ""
    if feat.ring or (feat.proxy and feat.neighbor_prior_fraud and feat.shared_device_cards_log > 0):
        return Pattern.undocumented.value, "shared proxy device profile across cards with confirmed fraud"
    if feat.structuring:
        return Pattern.undocumented.value, "repeated online purchases just under a $500 threshold within 40 minutes"
    if feat.testing_then_purchase or feat.micro_auth_burst:
        return Pattern.card_testing.value, ""
    if feat.out_of_region and not feat.online:
        return Pattern.out_of_region_use.value, ""
    if feat.mixed_channel and (feat.new_device or feat.prior_fraud_log > 0):
        return Pattern.account_takeover.value, ""
    if feat.online and feat.new_device:
        return Pattern.card_not_present_new_device.value, ""
    if feat.online:
        return Pattern.card_not_present_fraud.value, ""
    return (Pattern.account_takeover.value if feat.mixed_channel else Pattern.none.value), ""
