"""Assemble the official cases/<case_id>.json (data/ANSWER_FORMAT.md) and the internal record."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent import loop as L
from agent import policy as P
from agent import scoring as S
from agent.schema import AnswerFile, ConfidenceBreakdown, InternalCaseRecord, StoppingDecision
from mcp.trace import TraceRecorder

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"


def template_summary(inv: L.Investigation, d: dict[str, Any]) -> str:
    """Deterministic narrator slot; an LLM narrator (P3) may replace the prose but not the facts."""
    f = inv.features
    facts = [f"Case {inv.case.case_id} on card {inv.case.card_id}: verdict {d['verdict']} at probability {inv.probability:.2f} ({inv.archetype} playbook)."]
    if not f.flagged:
        facts.append(f"The graph returned no row for the flagged transaction {inv.case.flagged_txn_id} in the 30-day window, so device and amount context is missing.")
    if f.prior_fraud_log > 0:
        facts.append(f"The card carries prior confirmed-fraud cases ({', '.join(inv.similar_prior_cases[:3]) or 'see similar_prior_cases'}).")
    if f.region_history:
        facts.append("The card has prior history in the flagged billing region while home activity continued.")
    if f.new_device or f.proxy:
        facts.append("The flagged online transaction came from a device marked New for this account" + (" behind a proxy." if f.proxy else "."))
    if d["pattern"] == "undocumented":
        facts.append(f"Pattern: {d['pattern_basis']} (R9; not forced into a known category).")
    facts.append(f"Actions follow {', '.join(sorted({a['reason'].split(':')[0] for a in d['final']}))}.")
    return " ".join(facts[:6])


def pattern_description(d: dict[str, Any], inv: L.Investigation) -> str:
    if d["pattern"] != "undocumented":
        return ""
    return (f"Activity on {inv.case.card_id} shows {d['pattern_basis']}. It affects the cardholder {inv.case.customer_id}"
            f"{' and ' + str(len(inv.connected_card_ids)) + ' connected cards' if inv.connected_card_ids else ''}. "
            f"Found through {', '.join(sorted(inv.features.queries_seen))} on the graph.")


def sar_draft(inv: L.Investigation, d: dict[str, Any]) -> dict[str, Any]:
    txns = [S.attrs(t) for t in S.merge_blocks(inv.results.get("card_window")).get("transactions", [])]
    aff = [t for t in txns if str(t.get("txn_id")) in set(inv.affected_txn_ids)]
    dates = sorted(t["ts"][:10] for t in aff if t.get("ts")) or [inv.case.opened_at[:10]]
    subjects = [inv.case.customer_id, inv.case.card_id, *inv.connected_card_ids[:5], *inv.connected_device_profiles[:3]]
    who = f"Customer {inv.case.customer_id}, card {inv.case.card_id}"
    narrative = (
        f"{who} was used for {len(aff) or 1} transaction(s) totalling ${d['exposure']:,.2f} between {dates[0]} and {dates[-1]}. "
        f"The flagged transaction {inv.case.flagged_txn_id} was {inv.features.flagged.get('channel', 'recorded')}"
        f"{' in billing region ' + str(inv.features.flagged.get('addr1')) if inv.features.flagged.get('addr1') else ''}. "
        + (f"The device profile {inv.connected_device_profiles[0]} was marked New for this account. " if inv.connected_device_profiles and inv.features.new_device else "")
        + (f"The same device profile links to cards {', '.join(inv.connected_card_ids[:5])}. " if inv.connected_card_ids else "")
        + (f"Closed cases {', '.join(inv.similar_prior_cases[:3])} on this card were confirmed fraud. " if inv.features.prior_fraud_log > 0 and inv.similar_prior_cases else "")
        + (f"The cardholder denied the activity when asked. " if inv.features.customer_denied else "")
        + f"The pattern identified is {d['pattern']}{': ' + d['pattern_basis'] if d['pattern_basis'] else ''}. "
        f"The activity is suspicious because probability {inv.probability:.2f} rests on {len(inv.features.queries_seen)} independent graph evidence sources. "
        f"Recommended: {', '.join(a['action'] for a in d['final'])}."
    )
    return {"narrative": narrative, "subjects": list(dict.fromkeys(subjects)), "activity_dates": [dates[0], dates[-1]]}


def build(case_id: str, client: Any = None, write_graph: bool = True, tokens: int = 0) -> tuple[AnswerFile, InternalCaseRecord]:
    t0 = time.perf_counter()
    trace = TraceRecorder(case_id=case_id)
    client = client or L.get_client(trace)
    client.trace = trace  # one recorder per case, whichever backend the caller injected
    inv, trace = L.run_case(case_id, client, trace)
    d = L.decide(inv)
    sar = P.zero_out(P.sar_fields(d["final"], inv.probability, d["flags"], d["exposure"], sar_draft(inv, d)))
    summary = template_summary(inv, d)
    case_obj: dict[str, Any] = {
        "status": d["status"], "verdict": d["verdict"], "fraud_probability": inv.probability, "pattern": d["pattern"],
        "pattern_description": pattern_description(d, inv), "affected_txn_ids": inv.affected_txn_ids,
        "first_suspicious_txn_id": min(inv.affected_txn_ids, key=int) if inv.affected_txn_ids else "",
        "connected_card_ids": inv.connected_card_ids, "connected_device_profiles": inv.connected_device_profiles,
        "exposure_usd": d["exposure"], "evidence": inv.evidence, "similar_prior_cases": inv.similar_prior_cases,
        "summary": summary, "written_to_graph": False, "graph_case_id": "",
    }
    payload = {"case_id": case_id, "case": case_obj, "evidence_requests": d["requests"],
               "next_best_actions": {"initial": d["initial"], "final": d["final"], "what_changed": d["what_changed"]}, "sar": sar,
               "stop_reason": inv.stop_reason}
    if write_graph:
        ok, gid = L.write_back(inv, client, payload, summary, d)
        case_obj["written_to_graph"], case_obj["graph_case_id"] = ok, gid
        case_obj["evidence"] = inv.evidence
    answer = AnswerFile.model_validate({**payload, "tokens": tokens, "tool_calls": trace.tool_calls, "latency_s": round(time.perf_counter() - t0, 3)})
    record = InternalCaseRecord(
        answer=answer, trigger_type=inv.case.trigger_type, trigger_text=inv.case.trigger_text, opened_at=inv.case.opened_at,
        flagged_txn_id=inv.case.flagged_txn_id, card_id=inv.case.card_id, customer_id=inv.case.customer_id,
        flagged_risk_score=inv.case.risk_score, tool_trace=trace.to_tool_trace(),
        confidence_breakdown=ConfidenceBreakdown(**inv.breakdown) if inv.breakdown else None,
        decisions=[StoppingDecision(**x) for x in inv.decisions], uncertainty=f"archetype={inv.archetype}; backend={inv.backend}",
    )
    return answer, record


def write(answer: AnswerFile, out_dir: Path = CASES_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{answer.case_id}.json"
    text = answer.to_submission_json()
    assert_zero_out(json.loads(text))
    path.write_text(text, encoding="utf-8")
    return path


def assert_zero_out(data: dict[str, Any]) -> None:
    """Byte-level guard: a non-filed SAR leaves no narrative, subjects, amount or dates anywhere."""
    sar = data["sar"]
    if not sar["file"]:
        assert sar["narrative"] == "" and sar["subjects"] == [] and sar["total_amount_usd"] == 0 and sar["activity_dates"] == []
        assert "FILE_REPORT" not in {a["action"] for a in data["next_best_actions"]["final"]}
