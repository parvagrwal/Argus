"""Autonomous exam-period monitor (README D9).

Scans transactions.csv for exam-period (ts >= 2016-11-01) transactions with risk_score > 0.80,
excludes 20 benchmark cards, groups by card, and investigates the top 5 distinct cards.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from agent.answer import build, write
from agent.loop import CaseInput
from agent.schema import AnswerFile
from graph.card_id import build_card_map_from_csv

TRANSACTIONS_CSV = ROOT / "data" / "transactions.csv"
CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
BONUS_DIR = ROOT / "bonus_cases"


def run_monitor(live: bool = True) -> list[dict[str, Any]]:

    # Exclude 20 benchmark cards
    benchmark_cards: set[str] = set()
    if CASE_PACK_CSV.exists():
        with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                benchmark_cards.add(r["card_id"])

    # Build card map
    card_map = build_card_map_from_csv(TRANSACTIONS_CSV)

    # Scan for candidates: ts >= 2016-11-01 and risk_score > 0.80
    candidates: list[dict[str, Any]] = []
    cols = ["TransactionID", "customer_id", "card6", "ts", "risk_score"]
    for chunk in pd.read_csv(TRANSACTIONS_CSV, usecols=cols, chunksize=100_000):
        sub = chunk[(chunk["ts"] >= "2016-11-01") & (chunk["risk_score"] > 0.80)]
        for _, row in sub.iterrows():
            cid = card_map.card_id_for(row["customer_id"], row["card6"])
            if cid not in benchmark_cards:
                candidates.append({
                    "card_id": cid,
                    "customer_id": str(row["customer_id"]),
                    "TransactionID": str(row["TransactionID"]),
                    "ts": str(row["ts"]),
                    "risk_score": float(row["risk_score"]),
                })

    # Group by card; take up to 5 distinct cards ordered by max risk_score descending
    by_card: dict[str, dict[str, Any]] = {}
    for c in candidates:
        cid = c["card_id"]
        if cid not in by_card or c["risk_score"] > by_card[cid]["risk_score"]:
            by_card[cid] = c

    # Sort by max risk_score descending, tie-break on ts descending
    sorted_cards = sorted(by_card.values(), key=lambda x: (x["risk_score"], x["ts"]), reverse=True)[:5]

    BONUS_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []

    for i, sc in enumerate(sorted_cards, 1):
        bonus_id = f"BONUS_{i:03d}"
        tid = sc["TransactionID"]
        rs = sc["risk_score"]
        ts = sc["ts"]
        cid = sc["card_id"]
        cust = sc["customer_id"]

        case = CaseInput(
            case_id=bonus_id,
            opened_at=ts,
            trigger_type="risk_score",
            trigger_text=f"Autonomous monitor: risk_score {rs:.2f} on txn {tid} during exam period",
            flagged_txn_id=tid,
            card_id=cid,
            customer_id=cust,
            risk_score=rs,
        )

        answer, record = build(case, write_graph=True, memory=True)
        # Validate against AnswerFile
        AnswerFile.model_validate(answer.model_dump())
        out_path = write(answer, out_dir=BONUS_DIR)

        summary_rows.append({
            "bonus_id": bonus_id,
            "card": cid,
            "p": answer.case.fraud_probability,
            "verdict": str(getattr(answer.case.verdict, "value", answer.case.verdict)),
            "pattern": str(getattr(answer.case.pattern, "value", answer.case.pattern)),
            "path": str(out_path),
            "case_input": {
                "case_id": bonus_id,
                "opened_at": ts,
                "trigger_type": "risk_score",
                "trigger_text": f"Autonomous monitor: risk_score {rs:.2f} on txn {tid} during exam period",
                "flagged_txn_id": tid,
                "card_id": cid,
                "customer_id": cust,
                "risk_score": rs,
            },
        })

    import json
    (BONUS_DIR / "manifest.json").write_text(json.dumps([r["case_input"] for r in summary_rows], indent=2), encoding="utf-8")

    # Write bonus_cases/README.md
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    readme_content = f"""# Autonomous Exam-Period Monitor Cases

These cases were found by the autonomous exam-period monitor (README D9). They count toward Innovation, not accuracy.

- **Run Date**: {run_date}
- **Flag Rule**: `ts >= 2016-11-01` (exam period) AND `risk_score > 0.80`, excluding benchmark cards. Grouped by card, ordered by max `risk_score` descending (top 5 distinct cards).

## Investigated Bonus Cases
| Bonus ID | Card ID | Fraud Probability | Verdict | Pattern |
| :--- | :--- | :--- | :--- | :--- |
"""
    for row in summary_rows:
        readme_content += f"| `{row['bonus_id']}` | `{row['card']}` | {row['p']:.4f} | `{row['verdict']}` | `{row['pattern']}` |\n"

    (BONUS_DIR / "README.md").write_text(readme_content, encoding="utf-8")

    # Print summary table to stdout
    print(f"\n{'='*70}")
    print(f"{'BONUS MONITOR SUMMARY TABLE':^70}")
    print(f"{'='*70}")
    print(f"{'Bonus ID':<12} | {'Card ID':<12} | {'Prob':<8} | {'Verdict':<12} | {'Pattern':<20}")
    print(f"{'-'*12}-+-{'-'*12}-+-{'-'*8}-+-{'-'*12}-+-{'-'*20}")
    for row in summary_rows:
        print(f"{row['bonus_id']:<12} | {row['card']:<12} | {row['p']:<8.4f} | {row['verdict']:<12} | {row['pattern']:<20}")
    print(f"{'='*70}\n")

    return summary_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous exam-period monitor")
    parser.add_argument("--live", action="store_true", help="Run against live TigerGraph")
    args = parser.parse_args()
    run_monitor(live=args.live)
