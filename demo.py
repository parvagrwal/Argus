"""Demo CLI for Argus: live/offline investigations, economics, counterfactuals, and memory ablation."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent import policy as P
from agent import scoring as S
from agent.counterfactual import counterfactual
from agent.ev import economics
from agent.loop import CaseInput, decide, run_input
from fixtures import FixtureClient

CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
CASES_DIR = ROOT / "cases"
ABLATION_REPORT = ROOT / "ablation_report.json"


def run_single_demo(case_id: str, offline: bool = False) -> None:
    if offline:
        for var in ("TG_HOST", "TG_SECRET", "TG_PASSWORD", "TIGERGRAPH_HOST", "TIGERGRAPH_SECRET", "TIGERGRAPH_PASSWORD"):
            if os.environ.get(var):
                raise AssertionError(f"Offline mode requires {var} unset, but got {os.environ[var]!r}")
        client = FixtureClient(case_id)
    else:
        client = None

    case = CaseInput.load(case_id)
    inv, trace = run_input(case, client=client, memory=True)
    d = decide(inv)

    exposure = round(sum(
        float(S.attrs(t)["amount"])
        for t in S.merge_blocks(inv.results.get("card_window")).get("transactions", [])
        if str(S.attrs(t).get("txn_id")) in set(inv.affected_txn_ids)
    ), 2)

    econ = economics(inv.probability, exposure, inv.features)

    verdict = d["verdict"]
    if verdict in ("fraud", "legitimate"):
        cf = counterfactual(inv.features, S.DEFAULT_WEIGHTS, inv.breakdown.get("bias", -1.6), inv.probability, verdict)
        cf_sentence = cf["sentence"]
    else:
        cf_sentence = f"Verdict is {verdict}; counterfactual applies only to definitive fraud or legitimate verdicts."

    sar_actions = {a["action"] for a in d["final"]}
    sar_filed = "FILE_REPORT" in sar_actions

    tag = "[fixture] " if offline else ""
    print(f"{tag}==================================================")
    print(f"{tag}Investigation Summary for {case_id}")
    print(f"{tag}==================================================")
    print(f"{tag}Verdict:          {verdict}")
    print(f"{tag}Fraud Probability: {inv.probability:.4f}")
    print(f"{tag}Pattern:          {d['pattern']}")
    print(f"{tag}NBA Initial:      {', '.join(a['action'] for a in d['initial'])}")
    print(f"{tag}NBA Final:        {', '.join(a['action'] for a in d['final'])}")
    print(f"{tag}What Changed:     {d['what_changed']}")
    print(f"{tag}Evidence Count:   {len(inv.evidence)}")
    print(f"{tag}SAR Filed:        {'yes' if sar_filed else 'no'}")
    print(f"{tag}--------------------------------------------------")
    print(f"{tag}Economics:        {econ['reading']}")
    print(f"{tag}Counterfactual:   {cf_sentence}")
    print(f"{tag}==================================================")


def run_ablation(case_id: str) -> None:
    case = CaseInput.load(case_id)

    # 1. With memory
    inv_with, _ = run_input(case, memory=True)
    d_with = decide(inv_with)
    p_with = inv_with.probability
    v_with = d_with["verdict"]
    act_with = d_with["final"][0]["action"] if d_with["final"] else "NONE"

    # 2. Without memory
    inv_without, _ = run_input(case, memory=False)
    d_without = decide(inv_without)
    p_without = inv_without.probability
    v_without = d_without["verdict"]
    act_without = d_without["final"][0]["action"] if d_without["final"] else "NONE"

    delta_p = abs(p_with - p_without)
    changed = v_with != v_without
    sentence = f"Without case memory, fraud probability moves from {p_with:.2f} to {p_without:.2f} and the verdict {'changes from '+v_with+' to '+v_without if changed else 'is unchanged'}."

    print("==================================================")
    print(f"Memory Ablation Study for {case_id}")
    print("==================================================")
    print(f"{'Metric':<18} | {'With Memory':<15} | {'Without Memory':<15}")
    print(f"{'-'*18}-+-{'-'*15}-+-{'-'*15}")
    print(f"{'Probability':<18} | {p_with:<15.4f} | {p_without:<15.4f}")
    print(f"{'Verdict':<18} | {v_with:<15} | {v_without:<15}")
    print(f"{'Top Action':<18} | {act_with:<15} | {act_without:<15}")
    print(f"{'|Δp|':<18} | {delta_p:<15.4f} |")
    print("--------------------------------------------------")
    print(sentence)
    print("==================================================")


def run_ablation_sweep() -> None:
    print("Running memory ablation sweep over all 20 benchmark cases...")
    report: dict[str, Any] = {}

    cases: list[CaseInput] = []
    with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cases.append(CaseInput(
                r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                r["flagged_txn_id"], r["card_id"], r["customer_id"],
                float(r["risk_score"]) if r["risk_score"] else None,
            ))

    max_delta = -1.0
    max_case = ""

    for case in cases:
        cid = case.case_id
        # Read with-memory values from existing cases/<case_id>.json (do NOT re-run)
        existing_path = CASES_DIR / f"{cid}.json"
        if not existing_path.exists():
            raise FileNotFoundError(f"Existing case file {existing_path} not found")
        existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
        p_with = existing_data["case"]["fraud_probability"]
        v_with = existing_data["case"]["verdict"]

        # Run without memory live
        inv_no_mem, _ = run_input(case, memory=False)
        d_no_mem = decide(inv_no_mem)
        p_without = inv_no_mem.probability
        v_without = d_no_mem["verdict"]

        delta_p = round(abs(p_with - p_without), 4)
        if delta_p > max_delta:
            max_delta = delta_p
            max_case = cid

        report[cid] = {
            "p_with_memory": p_with,
            "p_without_memory": round(p_without, 4),
            "verdict_with": v_with,
            "verdict_without": v_without,
            "delta_p": delta_p,
            "verdict_changed": v_with != v_without,
        }
        print(f"{cid}: with={p_with:.4f} ({v_with}) -> without={p_without:.4f} ({v_without}), |Δp|={delta_p:.4f}")

    ABLATION_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nAblation report written to {ABLATION_REPORT}")
    print(f"Case with largest |Δp|: {max_case} (|Δp| = {max_delta:.4f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus Demo CLI")
    parser.add_argument("--case-id", default="HHG-014", help="Case ID to investigate (default: HHG-014)")
    parser.add_argument("--offline", action="store_true", help="Run offline using recorded fixtures")
    parser.add_argument("--ablate-memory", action="store_true", help="Compare run with and without memory")
    parser.add_argument("--ablate-sweep", action="store_true", help="Run ablation sweep across all 20 cases")
    args = parser.parse_args()

    if args.ablate_sweep:
        run_ablation_sweep()
    elif args.ablate_memory:
        run_ablation(args.case_id)
    else:
        run_single_demo(args.case_id, offline=args.offline)


if __name__ == "__main__":
    main()
