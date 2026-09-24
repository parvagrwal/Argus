"""Investigation loop: archetype playbooks, marginal-value stopping, evidence simulation, graph write-back."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from agent import policy as P
from agent import scoring as S
from agent.schema import Action, EvidenceRequestType
from mcp.fallback_rest import GraphUnavailable, get_client
from mcp.trace import TraceRecorder

ROOT = Path(__file__).resolve().parents[1]
CASE_PACK = ROOT / "data" / "case_pack.csv"
MAX_CALLS = 12
MARGINAL_GATE = 0.04  # expected |logit| gain below this is not worth one more graph call
QUERY_FEATURES: dict[str, list[str]] = {
    "card_window": ["risk_score", "new_device", "proxy", "online_burst_48h", "amount_ratio_log", "prior_fraud_log", "prior_cleared", "mixed_channel"],
    "velocity_check": ["micro_auth_burst", "testing_then_purchase", "structuring"],
    "region_profile": ["out_of_region", "region_history", "trip_pattern"],
    "device_neighbors": ["shared_device_cards_log", "neighbor_prior_fraud"],
    "detect_fraud_ring": ["ring"],
}
APPLY: dict[str, Callable[..., None]] = {
    "velocity_check": S.apply_velocity, "region_profile": S.apply_region,
    "device_neighbors": S.apply_device_neighbors, "detect_fraud_ring": S.apply_ring,
}


@dataclass
class Playbook:
    name: str
    plan: list[str]             # ordered queries after card_window
    deciding: str               # the single piece of evidence that settles the archetype
    early_stop: Callable[[S.Features, float], bool]


# Archetypes are assigned from the FIRST query's facts (priors, channel, identity), never from the case id.
PLAYBOOKS: dict[str, Playbook] = {
    "false_positive_trap": Playbook("false_positive_trap", ["region_profile", "velocity_check", "device_neighbors"],
                                    "region_profile: prior history in the flagged region while home activity continued",
                                    lambda f, p: f.region_history == 1.0 and p <= P.STOP_LOW),
    "fraud_heavy_priors": Playbook("fraud_heavy_priors", ["region_profile", "velocity_check", "device_neighbors", "detect_fraud_ring"],
                                   "region_profile / device_neighbors: does the flagged activity repeat the card's confirmed-fraud typology",
                                   lambda f, p: p >= P.STOP_HIGH and (f.out_of_region or f.new_device or f.mixed_channel)),
    "undocumented_ring": Playbook("undocumented_ring", ["device_neighbors", "detect_fraud_ring", "velocity_check", "region_profile"],
                                  "detect_fraud_ring: component of cards on the shared proxy device with confirmed fraud",
                                  lambda f, p: f.ring == 1.0),
    "cold_start": Playbook("cold_start", ["velocity_check", "device_neighbors", "region_profile"],
                           "velocity_check: a testing or burst sequence is the only evidence a history-less card can give",
                           lambda f, p: f.testing_then_purchase == 1.0),
    "cnp_default": Playbook("cnp_default", ["velocity_check", "device_neighbors", "region_profile", "detect_fraud_ring"],
                            "device_neighbors: New device shared with other cards, or a burst within 48h",
                            lambda f, p: (p >= P.STOP_HIGH or p <= P.STOP_LOW) and len(f.queries_seen) >= 3),
}


def choose_archetype(f: S.Features, trigger: str) -> str:
    if f.cold_start:
        return "cold_start"
    if f.proxy or trigger == "analyst_request":
        return "undocumented_ring"
    if f.prior_fraud_log >= 1.3:  # >= 3 confirmed-fraud priors (HHG-003 / HHG-007 are here, not false alarms)
        return "fraud_heavy_priors"
    if not f.online and f.prior_cleared:
        return "false_positive_trap"
    return "cnp_default"


def expected_gain(query: str, f: S.Features, p: float, weights: dict[str, float]) -> float:
    """Marginal value of one more call: reachable |weight| on still-unfilled features x current uncertainty."""
    unfilled = [k for k in QUERY_FEATURES.get(query, []) if f.vector().get(k, 0.0) == 0.0]
    uncertainty = 1.0 - abs(2 * p - 1)
    return round(sum(abs(weights.get(k, 0.0)) for k in unfilled) * uncertainty / 10.0, 4)


@dataclass
class CaseInput:
    case_id: str
    opened_at: str
    trigger_type: str
    trigger_text: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    risk_score: float | None

    @classmethod
    def load(cls, case_id: str, path: Path = CASE_PACK) -> "CaseInput":
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["case_id"] == case_id:
                    return cls(r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"], r["flagged_txn_id"],
                               r["card_id"], r["customer_id"], float(r["risk_score"]) if r["risk_score"] else None)
        raise KeyError(case_id)


@dataclass
class Investigation:
    case: CaseInput
    features: S.Features = field(default_factory=S.Features)
    probability: float = 0.0
    breakdown: dict[str, Any] = field(default_factory=dict)
    archetype: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    evidence_requests: list[dict[str, Any]] = field(default_factory=list)
    similar_prior_cases: list[str] = field(default_factory=list)
    affected_txn_ids: list[str] = field(default_factory=list)
    connected_card_ids: list[str] = field(default_factory=list)
    connected_device_profiles: list[str] = field(default_factory=list)
    stop_reason: str = ""
    backend: str = "mock"
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    memory: bool = True


def run_input(
    case: CaseInput,
    client: Any = None,
    trace: TraceRecorder | None = None,
    weights: dict[str, float] | None = None,
    memory: bool = True,
) -> tuple[Investigation, TraceRecorder]:
    trace = trace or TraceRecorder(case_id=case.case_id)
    client = client or get_client(trace)
    inv = Investigation(case=case, backend=getattr(client, "backend", "mock"), memory=memory)
    w = weights or S.DEFAULT_WEIGHTS
    end = case.opened_at
    start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    burst_start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(hours=78)).strftime("%Y-%m-%d %H:%M:%S")
    inv.features.customer_report = float(case.trigger_type == "customer_report")
    if case.risk_score is not None:
        inv.features.risk_score = case.risk_score

    def call(name: str, **params: Any) -> dict[str, Any]:
        if trace.tool_calls >= MAX_CALLS:
            raise RuntimeError("call cap")
        res = client.run_query(name, **params)
        inv.results[name] = res
        n = S.merge_blocks(res)
        entity_ids = [str(x) for x in (n.get("micro_auth_txn_ids") or []) + [case.card_id]] if name == "velocity_check" else [case.card_id]
        inv.evidence.append({"claim": f"{name} returned {'no rows' if not res.get('results') else 'graph facts'} for card {case.card_id}"
                             + (" [MOCK backend: not evidence]" if res.get("_mock") else ""),
                             "source": "graph", "ref": f"query:{name}({', '.join(f'{k}={v}' for k, v in params.items())})",
                             "entity_ids": entity_ids})
        return res

    def rescore(rule: str) -> None:
        inv.breakdown = S.score(inv.features, w)
        inv.probability = inv.breakdown["probability"]
        inv.decisions.append({"round": len(inv.decisions), "probability": inv.probability, "independent_evidence": len(inv.features.queries_seen),
                              "rule_fired": rule, "continue_investigating": True, "note": ""})

    try:
        res = call("card_window", card=case.card_id, window_start=start, window_end=end, max_rows=500)
        S.apply_card_window(inv.features, res, case.flagged_txn_id, end)
        if not memory:
            inv.features.prior_fraud_log = 0.0
            inv.features.prior_cleared = 0.0
        _harvest_card_window(inv, res)
        rescore("card_window")
        inv.archetype = choose_archetype(inv.features, case.trigger_type)
        book = PLAYBOOKS[inv.archetype]
        for q in book.plan:
            gain = expected_gain(q, inv.features, inv.probability, w)
            settled = (inv.probability >= P.STOP_HIGH or inv.probability <= P.STOP_LOW) and len(inv.features.queries_seen) >= S.MIN_INDEPENDENT_EVIDENCE
            if settled:
                inv.stop_reason = f"§6 hard stop: probability {inv.probability:.2f} beyond 0.85/0.15 with {len(inv.features.queries_seen)} independent graph evidence sources"
                break
            if book.early_stop(inv.features, inv.probability):
                inv.stop_reason = f"{inv.archetype}: deciding evidence found ({book.deciding}); further queries would not change the decision"
                break
            if gain < MARGINAL_GATE and len(inv.features.queries_seen) >= S.MIN_INDEPENDENT_EVIDENCE:
                inv.stop_reason = f"marginal-value gate: expected gain of {q} ({gain}) below {MARGINAL_GATE}; further steps unlikely to change the decision"
                break
            params = {"card": case.card_id, "window_start": burst_start if q == "velocity_check" else start, "window_end": end}
            if q == "region_profile":
                params["flagged_region"] = str(inv.features.flagged.get("addr1", "") or "")
            r = call(q, **params)
            APPLY[q](inv.features, r)
            _harvest(inv, q, r)
            rescore(q)
        else:
            inv.stop_reason = f"{inv.archetype} playbook exhausted ({len(book.plan) + 1} graph queries); no further query has expected gain above the gate"
    except RuntimeError:
        inv.stop_reason = f"12-call cap reached at probability {inv.probability:.2f}; decision taken on the evidence gathered"
    except GraphUnavailable as exc:
        inv.stop_reason = f"graph backend unavailable ({type(exc).__name__}); decision taken on the evidence gathered so far"
    if not inv.stop_reason:
        inv.stop_reason = "investigation ended after the playbook; further steps unlikely to change the decision"
    return inv, trace


def run_case(
    case_id: str,
    client: Any = None,
    trace: TraceRecorder | None = None,
    weights: dict[str, float] | None = None,
    memory: bool = True,
) -> tuple[Investigation, TraceRecorder]:
    case = CaseInput.load(case_id)
    return run_input(case, client=client, trace=trace, weights=weights, memory=memory)


def _harvest_card_window(inv: Investigation, res: dict[str, Any]) -> None:
    if getattr(inv, "memory", True):
        m = S.merge_blocks(res)
        priors = [S.attrs(p) for p in m.get("prior_cases", [])]
        inv.similar_prior_cases = [p["case_id"] for p in sorted(priors, key=lambda p: p.get("opened_at", ""), reverse=True)[:5]]
    else:
        inv.similar_prior_cases = []
    f = inv.features.flagged
    if f:
        inv.affected_txn_ids = [inv.case.flagged_txn_id]
        if f.get("device_profile"):
            inv.connected_device_profiles = [f["device_profile"]]


def _harvest(inv: Investigation, q: str, res: dict[str, Any]) -> None:
    m = S.merge_blocks(res)
    if q == "velocity_check":
        ids = [str(x) for x in (m.get("micro_auth_txn_ids") or []) + (m.get("followup_large_txn_ids") or [])]
        inv.affected_txn_ids = sorted(set(inv.affected_txn_ids) | set(ids))
    if q in ("device_neighbors", "detect_fraud_ring"):
        rows = [S.attrs(c) for c in m.get("connected_cards", []) + m.get("component", [])]
        cards = {c["card_id"] for c in rows if c.get("card_id") and c["card_id"] != inv.case.card_id}
        inv.connected_card_ids = sorted(set(inv.connected_card_ids) | cards)
        if getattr(inv, "memory", True):
            for c in rows:
                for prior in c.get("prior_fraud_cases") or []:
                    if prior not in inv.similar_prior_cases:
                        inv.similar_prior_cases.append(prior)
        devs = {S.attrs(d).get("profile") for d in m.get("devices", [])} | set(m.get("shared_devices") or [])
        inv.connected_device_profiles = sorted(set(inv.connected_device_profiles) | {d for d in devs if d})


def flags_from(inv: Investigation, exposure: float) -> P.Flags:
    f = inv.features
    return P.Flags(
        single_signal=len(f.queries_seen) < 2 or sum(1 for k, v in f.vector().items() if v > 0 and k not in ("risk_score", "online", "customer_report")) < 2,
        customer_denied=bool(f.customer_denied), customer_confirmed=bool(f.customer_confirmed),
        card_testing=bool(f.micro_auth_burst), cleared_purchase_over_100=bool(f.testing_then_purchase) and exposure > P.R5_CLEARED_PURCHASE,
        shared_origin=bool(f.neighbor_prior_fraud or f.ring), undocumented=S.classify(f, inv.probability)[0] == "undocumented",
        evidence_conflict=bool(f.region_history and (f.new_device or f.prior_fraud_log > 1.3) and 0.3 <= inv.probability < 0.7),
        cold_start=bool(f.cold_start), independent_evidence=len(f.queries_seen),
    )


def decide(inv: Investigation) -> dict[str, Any]:
    """Initial NBA -> evidence request (EV-ranked, simulated) -> final NBA. All deterministic."""
    exposure = round(sum(float(S.attrs(t)["amount"]) for t in S.merge_blocks(inv.results.get("card_window")).get("transactions", [])
                         if str(S.attrs(t).get("txn_id")) in set(inv.affected_txn_ids)), 2)
    flags = flags_from(inv, exposure)
    initial = [r.as_item(exposure) for r in P.recommend(inv.probability, flags, exposure)]
    requests: list[dict[str, Any]] = []
    response = ""
    if P.should_request_evidence(inv.probability, flags):
        ranked = P.rank_evidence_requests(inv.probability, flags, exposure)
        if ranked:
            req = ranked[0][0]
            outcome, text = P.simulate_response(inv.case.case_id, req, inv.probability)
            requests.append({"type": req.value, "asked_after_step": len(inv.decisions), "assumed_response": text})
            inv.evidence.append({"claim": f"Simulated {req.value} response: {outcome}", "source": "customer" if req is not EvidenceRequestType.analyst_info else "external",
                                 "ref": "evidence_request:1", "entity_ids": []})
            inv.features.customer_denied = float(outcome == "denied")
            inv.features.customer_confirmed = float(outcome == "confirmed")
            inv.breakdown = S.score(inv.features)
            inv.probability = inv.breakdown["probability"]
            response = outcome
            flags = flags_from(inv, exposure)
    verdict, status = P.verdict_for(inv.probability, flags)
    if verdict == "legitimate":
        exposure, inv.affected_txn_ids = 0.0, []
    final = [r.as_item(exposure) for r in P.recommend(inv.probability, flags, exposure)] if requests else list(initial)
    pattern, basis = S.classify(inv.features, inv.probability)
    if verdict == "legitimate":
        pattern, basis = "none", ""
    return {"exposure": exposure, "flags": flags, "initial": initial, "final": final, "requests": requests, "response": response,
            "verdict": verdict, "status": status, "pattern": pattern, "pattern_basis": basis,
            "what_changed": P.what_changed(initial, final, response)}


def write_back(inv: Investigation, client: Any, answer_payload: dict[str, Any], summary: str, d: dict[str, Any]) -> tuple[bool, str]:
    """write_fraud_case then get_case_with_evidence; emit only after payload read-back equality (AGENTS.md §8).
    Uses the allow-listed token path; the mock backend never counts as written."""
    if not getattr(inv, "memory", True):
        return False, ""
    if Action.CREATE_CASE.value not in {a["action"] for a in d["final"]}:
        return False, ""
    gid = f"ARGUS-{inv.case.case_id}-{int(time.time())}"
    payload = json.dumps(answer_payload, sort_keys=True, separators=(",", ":"))
    try:
        client.run_query("write_fraud_case", graph_case_id=gid, case_id=inv.case.case_id, card_id=inv.case.card_id, status=d["status"],
                         verdict=d["verdict"], fraud_probability=float(inv.probability), pattern=d["pattern"], exposure_usd=float(d["exposure"]),
                         summary=summary, affected_txn_ids=set(inv.affected_txn_ids), device_profiles=set(inv.connected_device_profiles),
                         prior_case_ids=set(inv.similar_prior_cases), payload_json=payload)
        back = client.run_query("get_case_with_evidence", graph_case_id=gid)
    except (GraphUnavailable, RuntimeError):
        return False, ""
    m = S.merge_blocks(back)
    rows = [S.attrs(r) for r in m.get("investigation_case", [])]
    ok = bool(rows) and rows[0].get("payload_json") == payload and getattr(client, "backend", "mock") == "tigergraph"
    if rows and rows[0].get("payload_json") == payload:
        inv.evidence.append({"claim": f"Case written to the graph as {gid} and read back byte-equal", "source": "graph",
                             "ref": f"query:get_case_with_evidence(graph_case_id={gid})", "entity_ids": [gid] if ok else []})
    return ok, gid if ok else ""
