"""Export offline web bundle for Vercel static frontend.

Replays all 20 benchmark cases and 5 bonus cases through the real pipeline using FixtureClient.
Must run with TigerGraph credentials unset.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Strict assertion: offline must run with TigerGraph credentials unset
TG_CRED_VARS = ["TG_HOST", "TG_SECRET", "TG_PASSWORD", "TIGERGRAPH_HOST", "TIGERGRAPH_SECRET", "TIGERGRAPH_PASSWORD"]
for var in TG_CRED_VARS:
    val = os.environ.get(var)
    if val:
        raise AssertionError(f"TigerGraph credential {var} is set ({val!r}). Offline export must run with credentials unset.")

from agent import policy as P
from agent import scoring as S
from agent.answer import pattern_description, sar_draft, template_summary
from agent.counterfactual import counterfactual
from agent.ev import economics
from agent.loop import CaseInput, decide, run_input
from agent.schema import AnswerFile, ConfidenceBreakdown, InternalCaseRecord, StoppingDecision
from fixtures import FixtureClient
from mcp.trace import TraceRecorder

CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
BONUS_DIR = ROOT / "bonus_cases"
OUTPUT_DIR = ROOT / "web" / "public" / "data"


def load_all_cases() -> list[CaseInput]:
    cases: list[CaseInput] = []
    if CASE_PACK_CSV.exists():
        with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cases.append(CaseInput(
                    r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                    r["flagged_txn_id"], r["card_id"], r["customer_id"],
                    float(r["risk_score"]) if r["risk_score"] else None,
                ))

    manifest_path = BONUS_DIR / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for r in data:
            cases.append(CaseInput(
                r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                r["flagged_txn_id"], r["card_id"], r["customer_id"],
                float(r["risk_score"]) if r["risk_score"] else None,
            ))
    return cases


def export_bundle() -> None:
    cases = load_all_cases()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Exporting web bundle for {len(cases)} cases to {OUTPUT_DIR}...")

    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for case in cases:
        cid = case.case_id
        client = FixtureClient(cid)
        trace = TraceRecorder(case_id=cid)
        client.trace = trace

        t0 = time.perf_counter()
        inv, trace = run_input(case, client=client, trace=trace, memory=True)
        d = decide(inv)
        sar = P.zero_out(P.sar_fields(d["final"], inv.probability, d["flags"], d["exposure"], sar_draft(inv, d)))
        summary = template_summary(inv, d)

        case_obj: dict[str, Any] = {
            "status": d["status"],
            "verdict": d["verdict"],
            "fraud_probability": inv.probability,
            "pattern": d["pattern"],
            "pattern_description": pattern_description(d, inv),
            "affected_txn_ids": inv.affected_txn_ids,
            "first_suspicious_txn_id": min(inv.affected_txn_ids, key=int) if inv.affected_txn_ids else "",
            "connected_card_ids": inv.connected_card_ids,
            "connected_device_profiles": inv.connected_device_profiles,
            "exposure_usd": d["exposure"],
            "evidence": inv.evidence,
            "similar_prior_cases": inv.similar_prior_cases,
            "summary": summary,
            "written_to_graph": False,
            "graph_case_id": "",
        }

        payload = {
            "case_id": cid,
            "case": case_obj,
            "evidence_requests": d["requests"],
            "next_best_actions": {
                "initial": d["initial"],
                "final": d["final"],
                "what_changed": d["what_changed"],
            },
            "sar": sar,
            "stop_reason": inv.stop_reason,
        }

        answer = AnswerFile.model_validate({
            **payload,
            "tokens": 0,
            "tool_calls": trace.tool_calls,
            "latency_s": round(time.perf_counter() - t0, 3),
        })

        record = InternalCaseRecord(
            answer=answer,
            trigger_type=inv.case.trigger_type,
            trigger_text=inv.case.trigger_text,
            opened_at=inv.case.opened_at,
            flagged_txn_id=inv.case.flagged_txn_id,
            card_id=inv.case.card_id,
            customer_id=inv.case.customer_id,
            flagged_risk_score=inv.case.risk_score,
            tool_trace=trace.to_tool_trace(),
            confidence_breakdown=ConfidenceBreakdown(**inv.breakdown) if inv.breakdown else None,
            decisions=[StoppingDecision(**x) for x in inv.decisions],
            uncertainty=f"archetype={inv.archetype}; backend={inv.backend}",
        )

        # Exposure sourced the same way flags_from sources it
        exposure = round(sum(
            float(S.attrs(t)["amount"])
            for t in S.merge_blocks(inv.results.get("card_window")).get("transactions", [])
            if str(S.attrs(t).get("txn_id")) in set(inv.affected_txn_ids)
        ), 2)

        # Compute economics and counterfactual from final decided state
        final_p = answer.case.fraud_probability
        final_verdict = answer.case.verdict.value if hasattr(answer.case.verdict, "value") else str(answer.case.verdict)

        econ = economics(final_p, exposure, inv.features)

        bundle: dict[str, Any] = {
            "answer": answer.model_dump(mode="json"),
            "internal_record": record.model_dump(mode="json"),
            "economics": econ,
        }

        if final_verdict in ("fraud", "legitimate"):
            cf = counterfactual(
                inv.features,
                S.DEFAULT_WEIGHTS,
                inv.breakdown.get("bias", -1.6),
                final_p,
                final_verdict,
            )
            bundle["counterfactual"] = cf
        else:
            print(f"[{cid}] [OMISSION] Counterfactual omitted: verdict is {final_verdict!r} (neither fraud nor legitimate).")

        bundle["meta"] = {
            "fixture": True,
            "recorded_at": recorded_at,
            "source": "fixture replay of live TigerGraph run through the real pipeline",
            "pipeline": "run_input",
        }

        out_path = OUTPUT_DIR / f"{cid}.json"
        out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        print(f"Wrote {cid} bundle to {out_path}")

    print("All bundles successfully exported.")


if __name__ == "__main__":
    export_bundle()
