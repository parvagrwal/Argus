"""Fit scoring weights on the 5,565 closed cases from data/closed_cases_history.csv.

Extracts features using live TigerGraph queries matching agent/loop.py semantics,
fits L2-regularised logistic regression, and produces calibration report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.scoring as S
from mcp.fallback_rest import TGConfig, GraphClient, get_client

CLOSED_CASES_CSV = ROOT / "data" / "closed_cases_history.csv"
CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
CALIBRATION_DIR = ROOT / "scripts" / "calibration"
FITTED_WEIGHTS_JSON = CALIBRATION_DIR / "fitted_weights.json"
REPORT_MD = CALIBRATION_DIR / "report.md"
CACHE_JSONL = CALIBRATION_DIR / "features_cache.jsonl"

# --------------------------------------------------------------------------------------
# Keyword Extraction Rules for Analyst Notes
# --------------------------------------------------------------------------------------

RE_DENIED = re.compile(r"(denied|did not make|unrecognized|not authorized|none of which)", re.IGNORECASE)
RE_CONFIRMED = re.compile(r"(confirmed travel|cardholder confirmed|confirmed the purchase|confirmed the transaction)", re.IGNORECASE)
RE_REPORT = re.compile(r"(reported|dispute)", re.IGNORECASE)


def parse_analyst_notes(notes: str) -> dict[str, float]:
    """Parse analyst notes with explicit documented keyword rules."""
    denied = 1.0 if bool(RE_DENIED.search(notes)) else 0.0
    confirmed = 1.0 if bool(RE_CONFIRMED.search(notes)) else 0.0
    report = 1.0 if bool(RE_REPORT.search(notes)) else 0.0
    return {
        "customer_denied": denied,
        "customer_confirmed": confirmed,
        "customer_report": report,
    }


# --------------------------------------------------------------------------------------
# AUC and Statistical Metrics
# --------------------------------------------------------------------------------------


def compute_auc(probs: list[float], labels: list[int]) -> float:
    """Rank-based ROC-AUC (Mann-Whitney U statistic). Mathematically exact for in-sample evaluation."""
    paired = sorted(zip(probs, labels), key=lambda x: x[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ranks = [0.0] * len(paired)
    i = 0
    while i < len(paired):
        j = i
        while j < len(paired) and paired[j][0] == paired[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j
    sum_ranks_pos = sum(r for r, (_, y) in zip(ranks, paired) if y == 1)
    return round((sum_ranks_pos - (n_pos * (n_pos + 1)) / 2.0) / (n_pos * n_neg), 4)


# --------------------------------------------------------------------------------------
# Single Case Feature Extractor
# --------------------------------------------------------------------------------------


def extract_features_for_case(
    client: GraphClient,
    card_id: str,
    flagged_txn_id: str,
    opened_at: str,
    analyst_notes: str,
    trigger_type: str = "",
    risk_score: float | None = None,
) -> S.Features:
    end = opened_at
    start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    burst_start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(hours=78)).strftime("%Y-%m-%d %H:%M:%S")

    feat = S.Features()

    # Base trigger signals if provided
    if trigger_type == "customer_report":
        feat.customer_report = 1.0
    if risk_score is not None:
        feat.risk_score = float(risk_score)

    # 1. card_window
    res_cw = client.run_query("card_window", card=card_id, window_start=start, window_end=end, max_rows=500)
    if res_cw.get("_mock"):
        raise RuntimeError(f"Mock backend detected on card_window for {card_id}")
    S.apply_card_window(feat, res_cw, flagged_txn_id, end)

    # 2. velocity_check
    res_vc = client.run_query("velocity_check", card=card_id, window_start=burst_start, window_end=end)
    if res_vc.get("_mock"):
        raise RuntimeError(f"Mock backend detected on velocity_check for {card_id}")
    S.apply_velocity(feat, res_vc)

    # 3. region_profile
    flagged_region = str(feat.flagged.get("addr1", "") or "")
    res_rp = client.run_query("region_profile", card=card_id, window_start=start, window_end=end, flagged_region=flagged_region)
    if res_rp.get("_mock"):
        raise RuntimeError(f"Mock backend detected on region_profile for {card_id}")
    S.apply_region(feat, res_rp)

    # 4. device_neighbors
    res_dn = client.run_query("device_neighbors", card=card_id, window_start=start, window_end=end)
    if res_dn.get("_mock"):
        raise RuntimeError(f"Mock backend detected on device_neighbors for {card_id}")
    S.apply_device_neighbors(feat, res_dn)

    # 5. detect_fraud_ring
    res_dr = client.run_query("detect_fraud_ring", card=card_id, window_start=start, window_end=end)
    if res_dr.get("_mock"):
        raise RuntimeError(f"Mock backend detected on detect_fraud_ring for {card_id}")
    S.apply_ring(feat, res_dr)

    # Parse analyst notes for keyword features
    if analyst_notes:
        kw_features = parse_analyst_notes(analyst_notes)
        if kw_features["customer_denied"] > 0:
            feat.customer_denied = kw_features["customer_denied"]
        if kw_features["customer_confirmed"] > 0:
            feat.customer_confirmed = kw_features["customer_confirmed"]
        if kw_features["customer_report"] > 0:
            feat.customer_report = kw_features["customer_report"]

    # Cold start check: 1 if card_window shows no transaction strictly before opened_at, else 0
    m_cw = S.merge_blocks(res_cw)
    txns = [S.attrs(t) for t in m_cw.get("transactions", [])]
    has_prior_txns = any(t.get("ts", "") < opened_at for t in txns if str(t.get("txn_id")) != flagged_txn_id)
    feat.cold_start = 0.0 if has_prior_txns else 1.0

    return feat


# --------------------------------------------------------------------------------------
# Processing Loop
# --------------------------------------------------------------------------------------


def process_dataset(max_workers: int = 4) -> tuple[list[tuple[S.Features, int]], dict[str, int], list[tuple[str, str]]]:
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

    # Load cache if exists
    cached_vectors: dict[str, tuple[dict[str, float], int]] = {}
    if CACHE_JSONL.exists():
        with open(CACHE_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    cached_vectors[item["case_id"]] = (item["vector"], item["label"])
        print(f"Loaded {len(cached_vectors)} pre-computed feature vectors from cache.")

    # Read closed cases CSV
    raw_rows = []
    with open(CLOSED_CASES_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            raw_rows.append(r)

    total_cases = len(raw_rows)
    print(f"Starting processing for {total_cases} closed cases...")

    cache_file = open(CACHE_JSONL, "a", encoding="utf-8")
    cache_lock = threading.Lock()

    cfg = TGConfig.from_env()
    dataset: list[tuple[S.Features, int]] = []
    kw_counts = {"denied": 0, "confirmed": 0, "report": 0}
    skips: list[tuple[str, str]] = []
    completed_counter = len(cached_vectors)

    # Thread-local storage for GraphClient
    thread_local = threading.local()

    def get_thread_client() -> GraphClient:
        if not hasattr(thread_local, "client"):
            thread_local.client = GraphClient(cfg)
        return thread_local.client

    def process_row(row: dict[str, str]) -> tuple[str, dict[str, float] | None, int | None, str | None]:
        cid = row["case_id"]
        outcome = row.get("outcome", "").strip()
        if outcome == "confirmed_fraud":
            label = 1
        elif outcome == "cleared":
            label = 0
        else:
            return cid, None, None, f"Unknown outcome '{outcome}'"

        if cid in cached_vectors:
            vec, cached_label = cached_vectors[cid]
            return cid, vec, cached_label, None

        card_id = row.get("card_id", "").strip()
        opened_at = row.get("opened_at", "").strip()
        notes = row.get("analyst_notes", "").strip()

        fid = row.get("first_fraud_txn_id", "").strip()
        if not fid:
            txns = [t.strip() for t in row.get("txn_ids", "").split("|") if t.strip()]
            fid = txns[0] if txns else ""

        if not fid or not card_id or not opened_at:
            return cid, None, None, f"Missing critical fields (card={card_id}, fid={fid}, opened_at={opened_at})"

        client = get_thread_client()
        try:
            feat = extract_features_for_case(
                client=client,
                card_id=card_id,
                flagged_txn_id=fid,
                opened_at=opened_at,
                analyst_notes=notes,
            )
            vec = feat.vector()
            return cid, vec, label, None
        except Exception as exc:
            return cid, None, None, f"Query error: {exc}"

    rows_to_process = [r for r in raw_rows if r["case_id"] not in cached_vectors]

    # Process cached items first
    for r in raw_rows:
        cid = r["case_id"]
        notes = r.get("analyst_notes", "")
        if RE_DENIED.search(notes):
            kw_counts["denied"] += 1
        if RE_CONFIRMED.search(notes):
            kw_counts["confirmed"] += 1
        if RE_REPORT.search(notes):
            kw_counts["report"] += 1

        if cid in cached_vectors:
            vec, label = cached_vectors[cid]
            f = S.Features(**{k: v for k, v in vec.items() if hasattr(S.Features, k)})
            dataset.append((f, label))

    # Process remaining rows with thread pool
    if rows_to_process:
        print(f"Running queries for {len(rows_to_process)} cases across {max_workers} worker threads...")
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_case = {executor.submit(process_row, r): r["case_id"] for r in rows_to_process}
            for fut in concurrent.futures.as_completed(future_to_case):
                cid, vec, label, skip_reason = fut.result()
                completed_counter += 1
                if skip_reason:
                    skips.append((cid, skip_reason))
                else:
                    with cache_lock:
                        cache_file.write(json.dumps({"case_id": cid, "label": label, "vector": vec}) + "\n")
                        cache_file.flush()
                    f = S.Features(**{k: v for k, v in vec.items() if hasattr(S.Features, k)})
                    dataset.append((f, label))

                if completed_counter % 250 == 0 or completed_counter == total_cases:
                    elapsed = time.perf_counter() - t0
                    print(f"Progress: {completed_counter}/{total_cases} cases processed ({elapsed:.1f}s elapsed)...")

    cache_file.close()
    return dataset, kw_counts, skips


# --------------------------------------------------------------------------------------
# Benchmark Re-Scoring
# --------------------------------------------------------------------------------------


def rescore_benchmark_cases(client: GraphClient, fitted_weights: dict[str, float], fitted_bias: float) -> list[dict[str, Any]]:
    results = []
    with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
        cases = list(csv.DictReader(fh))

    for c in cases:
        cid = c["case_id"]
        feat = extract_features_for_case(
            client=client,
            card_id=c["card_id"],
            flagged_txn_id=c["flagged_txn_id"],
            opened_at=c["opened_at"],
            analyst_notes="",
            trigger_type=c["trigger_type"],
            risk_score=float(c["risk_score"]) if c.get("risk_score") else None,
        )

        prior_score = S.score(feat, S.DEFAULT_WEIGHTS, S.DEFAULT_BIAS)
        fitted_score = S.score(feat, fitted_weights, fitted_bias)

        prior_p = prior_score["probability"]
        fitted_p = fitted_score["probability"]

        def band(p: float) -> str:
            if p >= 0.85:
                return "fraud (>=0.85)"
            if p <= 0.15:
                return "legitimate (<=0.15)"
            return "uncertain (0.15-0.85)"

        prior_band = band(prior_p)
        fitted_band = band(fitted_p)
        flip = prior_band != fitted_band

        results.append({
            "case_id": cid,
            "prior_prob": prior_p,
            "fitted_prob": fitted_p,
            "prior_band": prior_band,
            "fitted_band": fitted_band,
            "flip": flip,
        })
    return results


# --------------------------------------------------------------------------------------
# Report Generator
# --------------------------------------------------------------------------------------


def generate_report(
    fitted_weights: dict[str, float],
    fitted_bias: float,
    prior_auc: float,
    fitted_auc: float,
    prior_cal: list[dict[str, Any]],
    fitted_cal: list[dict[str, Any]],
    benchmark_rescore: list[dict[str, Any]],
    kw_counts: dict[str, int],
    skips: list[tuple[str, str]],
    n_samples: int,
) -> str:
    lines = [
        "# Model Calibration Report — Fitted Weights on Closed Cases History\n",
        f"**Dataset**: `data/closed_cases_history.csv` ({n_samples} cases fitted)",
        f"**Methodology**: L2-regularised logistic regression (`iters=2000, l2=0.05, lr=0.05`), rank-based ROC-AUC (in-sample).",
        "",
        "> [!NOTE]",
        "> **Caveat (Architect judgment baked in)**: Feature extraction replicates the live pipeline semantics exactly, including counting all prior closed cases on each card rather than strictly time-bounding historical case references. This guarantees that fitted weights align mathematically with the inference pipeline.\n",
        "## 1. Executive Summary\n",
        f"- **In-Sample ROC-AUC**: Prior `{prior_auc:.4f}` → Fitted `{fitted_auc:.4f}` (Delta: `{fitted_auc - prior_auc:+.4f}`)",
        f"- **Prior Bias**: `{S.DEFAULT_BIAS}` | **Fitted Bias**: `{fitted_bias:.4f}`",
        f"- **Benchmark Cases Re-Score**: {sum(1 for r in benchmark_rescore if r['flip'])} verdict band flips observed at 0.85/0.15 thresholds.",
        f"- **Total Rows Skipped**: {len(skips)}\n",
        "## 2. Coefficient Comparison (Sorted by |Delta|)\n",
        "| Feature | Prior Weight | Fitted Weight | Delta (Fitted - Prior) | |Delta| |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    all_features = sorted(
        list(set(list(S.DEFAULT_WEIGHTS.keys()) + list(fitted_weights.keys()))),
        key=lambda k: abs(fitted_weights.get(k, 0.0) - S.DEFAULT_WEIGHTS.get(k, 0.0)),
        reverse=True,
    )

    for k in all_features:
        pw = S.DEFAULT_WEIGHTS.get(k, 0.0)
        fw = fitted_weights.get(k, 0.0)
        delta = fw - pw
        lines.append(f"| `{k}` | {pw:.4f} | {fw:.4f} | {delta:+.4f} | {abs(delta):.4f} |")

    lines.extend([
        "",
        "## 3. Calibration Reliability Table (10 Bins)\n",
        "### Prior Weights Reliability",
        "| Bin Range | Samples (n) | Mean Predicted Prob | Observed Fraud Rate |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for b in prior_cal:
        lines.append(f"| [{b['bin_lo']:.1f}, {b['bin_hi']:.1f}) | {b['n']} | {b['mean_pred']:.4f} | {b['observed']:.4f} |")

    lines.extend([
        "",
        "### Fitted Weights Reliability",
        "| Bin Range | Samples (n) | Mean Predicted Prob | Observed Fraud Rate |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for b in fitted_cal:
        lines.append(f"| [{b['bin_lo']:.1f}, {b['bin_hi']:.1f}) | {b['n']} | {b['mean_pred']:.4f} | {b['observed']:.4f} |")

    lines.extend([
        "",
        "## 4. Benchmark 20 Cases Re-Score (Compute-Only Evaluation)\n",
        "| Case ID | Prior Prob | Fitted Prob | Prior Band | Fitted Band | Flip? |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for r in benchmark_rescore:
        flip_mark = "**FLIP**" if r["flip"] else "No"
        lines.append(f"| `{r['case_id']}` | {r['prior_prob']:.4f} | {r['fitted_prob']:.4f} | {r['prior_band']} | {r['fitted_band']} | {flip_mark} |")

    lines.extend([
        "",
        "## 5. Keyword Rules Hit Counts & Skips\n",
        "- **`customer_denied` keyword matches**: " + str(kw_counts["denied"]),
        "- **`customer_confirmed` keyword matches**: " + str(kw_counts["confirmed"]),
        "- **`customer_report` keyword matches**: " + str(kw_counts["report"]),
        f"- **Total Skips**: {len(skips)}",
    ])

    if skips:
        lines.append("\n### Skip List Details")
        for cid, reason in skips:
            lines.append(f"- **{cid}**: {reason}")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit scoring weights on closed cases history")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")
    args = parser.parse_args()

    # Step 1: Process dataset
    dataset, kw_counts, skips = process_dataset(max_workers=args.workers)
    if not dataset:
        print("ERROR: No valid data points extracted.")
        return 1

    print(f"\nExtracted {len(dataset)} valid (features, outcome) rows. Fitting logistic regression...")

    # Step 2: Fit weights
    t_fit_start = time.perf_counter()
    fitted_w, fitted_b = S.fit_weights(dataset, l2=0.05, iters=2000, lr=0.05)
    print(f"Gradient descent complete in {time.perf_counter() - t_fit_start:.2f}s.")

    # Save fitted weights
    out_payload = {
        "weights": {k: round(v, 4) for k, v in fitted_w.items()},
        "bias": round(fitted_b, 4),
    }
    FITTED_WEIGHTS_JSON.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(f"Saved fitted weights to {FITTED_WEIGHTS_JSON}")

    # Step 3: Compute AUC and calibration tables
    labels = [y for _, y in dataset]
    prior_probs = [S.score(f, S.DEFAULT_WEIGHTS, S.DEFAULT_BIAS)["probability"] for f, _ in dataset]
    fitted_probs = [S.score(f, fitted_w, fitted_b)["probability"] for f, _ in dataset]

    prior_auc = compute_auc(prior_probs, labels)
    fitted_auc = compute_auc(fitted_probs, labels)

    prior_cal = S.calibration_table(prior_probs, labels, bins=10)
    fitted_cal = S.calibration_table(fitted_probs, labels, bins=10)

    # 20-case re-score
    print("Re-scoring 20 benchmark cases with fitted weights...")
    client = get_client()
    benchmark_rescore = rescore_benchmark_cases(client, fitted_w, fitted_b)
    flips = [r for r in benchmark_rescore if r["flip"]]

    # Write report
    report_text = generate_report(
        fitted_weights=fitted_w,
        fitted_bias=fitted_b,
        prior_auc=prior_auc,
        fitted_auc=fitted_auc,
        prior_cal=prior_cal,
        fitted_cal=fitted_cal,
        benchmark_rescore=benchmark_rescore,
        kw_counts=kw_counts,
        skips=skips,
        n_samples=len(dataset),
    )
    REPORT_MD.write_text(report_text, encoding="utf-8")
    print(f"Saved calibration report to {REPORT_MD}")

    # Step 4: Console Summary
    print("\n" + "=" * 60)
    print("CALIBRATION SUMMARY")
    print("=" * 60)
    print(f"AUC: prior {prior_auc:.4f} -> fitted {fitted_auc:.4f} (in-sample)")
    print(f"Verdict flips at 0.85/0.15 thresholds: {len(flips)} case(s)")
    if flips:
        for f_case in flips:
            print(f"  - {f_case['case_id']}: prior {f_case['prior_prob']:.4f} ({f_case['prior_band']}) -> fitted {f_case['fitted_prob']:.4f} ({f_case['fitted_band']})")
    else:
        print("  - None (0 flips)")
    print(f"Total skips: {len(skips)}")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
