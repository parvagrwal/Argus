"""Run pipeline for all 20 benchmark cases from data/case_pack.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import answer
from agent.schema import AnswerFile

CASE_PACK = ROOT / "data" / "case_pack.csv"
CASES_DIR = ROOT / "cases"


def load_case_ids(case_pack_path: Path = CASE_PACK) -> list[str]:
    with open(case_pack_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [row["case_id"] for row in reader if row.get("case_id")]


def run_all(force: bool = False, live: bool = False) -> list[dict]:
    if live:
        os.environ.pop("ARGUS_FORCE_MOCK", None)
    else:
        os.environ["ARGUS_FORCE_MOCK"] = "1"

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    case_ids = load_case_ids()
    results = []

    for case_id in case_ids:
        target_file = CASES_DIR / f"{case_id}.json"
        is_cached = target_file.exists() and not force

        if is_cached:
            data = json.loads(target_file.read_text(encoding="utf-8"))
            ans = AnswerFile.model_validate(data)
        else:
            ans, _ = answer.build(case_id, write_graph=True)
            answer.write(ans, out_dir=CASES_DIR)

        results.append({
            "case_id": ans.case_id,
            "verdict": ans.case.verdict,
            "fraud_probability": round(ans.case.fraud_probability, 4),
            "pattern": ans.case.pattern,
            "status": ans.case.status,
            "tool_calls": ans.tool_calls,
            "sar_file": ans.sar.file,
            "cached": is_cached,
        })

    return results


def print_summary_table(results: list[dict]) -> None:
    headers = ["case_id", "verdict", "fraud_prob", "pattern", "status", "tool_calls", "sar.file"]
    widths = [10, 14, 12, 28, 18, 12, 10]

    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths))
    sep_line = "-+-".join("-" * w for w in widths)

    print("\n" + header_line)
    print(sep_line)
    for r in results:
        prob_str = f"{r['fraud_probability']:.4f}"
        sar_str = "True" if r["sar_file"] else "False"
        row_line = " | ".join([
            f"{r['case_id']:<{widths[0]}}",
            f"{r['verdict']:<{widths[1]}}",
            f"{prob_str:<{widths[2]}}",
            f"{r['pattern']:<{widths[3]}}",
            f"{r['status']:<{widths[4]}}",
            f"{str(r['tool_calls']):<{widths[5]}}",
            f"{sar_str:<{widths[6]}}",
        ])
        print(row_line)
    print(sep_line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fraud investigation pipeline on all benchmark cases")
    parser.add_argument("--force", action="store_true", help="Overwrite existing case files in cases/")
    parser.add_argument("--live", action="store_true", help="Run against live TigerGraph instead of mock")
    args = parser.parse_args()

    results = run_all(force=args.force, live=args.live)
    print_summary_table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
