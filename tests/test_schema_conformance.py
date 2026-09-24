"""agent/schema.py vs the official answer format (data/ANSWER_FORMAT.md, README wins) and the
separation between the official writer (integer tool_calls) and the internal trace."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent import schema as S
from mcp import fallback_rest as fr
from mcp.trace import TraceRecorder

ROOT = Path(__file__).resolve().parents[1]
ANSWER_FORMAT = (ROOT / "data" / "ANSWER_FORMAT.md").read_text(encoding="utf-8")

OFFICIAL_TOP = ["case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"]
OFFICIAL_CASE = [
    "status", "verdict", "fraud_probability", "pattern", "pattern_description", "affected_txn_ids",
    "first_suspicious_txn_id", "connected_card_ids", "connected_device_profiles", "exposure_usd", "evidence",
    "similar_prior_cases", "summary", "written_to_graph", "graph_case_id",
]
OFFICIAL_SAR = ["file", "reason", "narrative", "subjects", "total_amount_usd", "activity_dates"]
OFFICIAL_NBA = ["initial", "final", "what_changed"]
OFFICIAL_EVIDENCE = ["claim", "source", "ref", "entity_ids"]
OFFICIAL_REQUEST = ["type", "asked_after_step", "assumed_response"]
OFFICIAL_ACTION_ITEM = ["action", "route", "reason"]


def _md_table_fields(section_heading: str) -> list[str]:
    """First-column code names of the markdown table directly under a heading in ANSWER_FORMAT.md."""
    m = re.search(rf"^##+\s+{re.escape(section_heading)}\s*$(.*?)(?=^##+\s|\Z)", ANSWER_FORMAT, re.S | re.M)
    assert m, section_heading
    return re.findall(r"^\|\s*`([a-z_]+)`\s*\|", m.group(1), re.M)


def test_top_level_keys_match_readme_exactly():
    assert list(S.AnswerFile.model_fields) == OFFICIAL_TOP
    assert _md_table_fields("Top level") == OFFICIAL_TOP


def test_case_keys_match_readme_exactly():
    assert list(S.Case.model_fields) == OFFICIAL_CASE
    assert _md_table_fields("Part 1: `case`") == OFFICIAL_CASE


def test_sar_and_nba_keys_match_readme_exactly():
    assert list(S.SAR.model_fields) == OFFICIAL_SAR
    assert _md_table_fields("Part 2: `sar`") == OFFICIAL_SAR
    assert list(S.NextBestActions.model_fields) == OFFICIAL_NBA
    assert _md_table_fields("Part 3: `next_best_actions`") == OFFICIAL_NBA
    assert list(S.Evidence.model_fields) == OFFICIAL_EVIDENCE
    assert list(S.EvidenceRequest.model_fields) == OFFICIAL_REQUEST
    assert list(S.RecommendedAction.model_fields) == OFFICIAL_ACTION_ITEM


def test_enums_use_readme_values():
    assert {p.value for p in S.Pattern} == {
        "card_testing", "card_not_present_fraud", "card_not_present_new_device", "out_of_region_use",
        "account_takeover", "undocumented", "none",
    }
    assert "legitimate" not in {p.value for p in S.Pattern}  # D-04: `none`, not `legitimate`
    assert {v.value for v in S.Verdict} == {"fraud", "legitimate", "uncertain"}
    assert {s.value for s in S.Status} == {"open", "closed_fraud", "closed_legitimate", "escalated"}
    assert {r.value for r in S.Route} == {"auto", "L1", "L2"}
    assert {e.value for e in S.EvidenceSource} == {"graph", "document", "customer", "external"}
    assert {t.value for t in S.EvidenceRequestType} == {"customer_validation", "step_up_auth", "analyst_info"}
    assert len(S.Action) == 14 and "REQUEST_EVIDENCE" not in {a.value for a in S.Action}  # D-11


def test_policy_routes_are_deterministic_and_match_section_2():
    assert S.BLOCK_CARD_L2_THRESHOLD_USD == 2500.0
    assert S.route_for(S.Action.FILE_REPORT, 0) == S.Route.L2
    assert S.route_for(S.Action.BLOCK_ALL_CARDS, 0) == S.Route.L2
    assert S.route_for(S.Action.DECLINE_TRANSACTION, 10_000) == S.Route.L1
    assert S.route_for(S.Action.BLOCK_CARD, 2500.0) == S.Route.L1
    assert S.route_for(S.Action.BLOCK_CARD, 2500.01) == S.Route.L2
    for a in S.AUTO_ACTIONS:
        assert S.route_for(a, 1e9) == S.Route.auto


def test_readme_examples_validate_and_roundtrip():
    for ex in (S.README_EXAMPLE, S.MINIMAL_LEGITIMATE_EXAMPLE):
        a = S.AnswerFile.model_validate(ex)
        text = a.to_submission_json()
        data = json.loads(text)
        assert list(data) == OFFICIAL_TOP and list(data["case"]) == OFFICIAL_CASE
        assert isinstance(data["tool_calls"], int) and isinstance(data["tokens"], int)
        assert isinstance(data["latency_s"], (int, float)) and data["stop_reason"]
        assert S.AnswerFile.model_validate_json(text) == a
        assert text.endswith("\n")


def test_official_file_forbids_internal_keys():
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["tool_trace"] = []
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["confidence_score"] = 0.9
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["case"]["confidence_breakdown"] = {}
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)


def test_cross_field_rules_enforced():
    # sar.file must agree with FILE_REPORT in final
    bad = copy.deepcopy(S.MINIMAL_LEGITIMATE_EXAMPLE)
    bad["sar"] = {"file": True, "reason": "r", "narrative": "n " * 6, "subjects": ["C1"], "total_amount_usd": 1,
                  "activity_dates": ["2016-01-01", "2016-01-02"]}
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    # legitimate => affected empty, exposure 0
    bad = copy.deepcopy(S.MINIMAL_LEGITIMATE_EXAMPLE)
    bad["case"]["affected_txn_ids"] = ["3553342"]
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    # no evidence requests => final == initial
    bad = copy.deepcopy(S.MINIMAL_LEGITIMATE_EXAMPLE)
    bad["next_best_actions"]["final"] = [{"action": "MONITOR_CARD", "route": "auto", "reason": "r"}]
    bad["next_best_actions"]["what_changed"] = "changed"
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    # undocumented requires a description
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["case"]["pattern"] = "undocumented"
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    # wrong route can never serialise
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["next_best_actions"]["final"][0]["route"] = "auto"  # BLOCK_CARD
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)


def test_internal_record_holds_trace_and_official_file_holds_only_the_count():
    rec = TraceRecorder(case_id="HHG-017")
    m = fr.MockGraphClient(trace=rec)
    for _ in range(9):
        m.run_query("card_window", card="C00377-K1", window_start="2016-11-14 00:00:00", window_end="2016-11-15 00:00:00")
    answer = S.AnswerFile.model_validate({**S.README_EXAMPLE, **rec.official_counts(), "latency_s": 18.7})
    assert answer.tool_calls == 9
    internal = S.InternalCaseRecord(
        answer=answer, trigger_type="customer_report", trigger_text="t", opened_at="2016-11-14 16:31:00",
        flagged_txn_id="3450629", card_id="C00377-K1", customer_id="C00377", tool_trace=rec.to_tool_trace(),
    )
    assert len(internal.tool_trace) == answer.tool_calls
    official = json.loads(answer.to_submission_json())
    assert "tool_trace" not in json.dumps(official)
    assert set(official) == set(OFFICIAL_TOP)
    # a trace/count mismatch is rejected
    with pytest.raises(ValidationError):
        S.InternalCaseRecord(
            answer=answer, trigger_type="x", trigger_text="t", opened_at="o", flagged_txn_id="f", card_id="c",
            customer_id="u", tool_trace=rec.to_tool_trace()[:3],
        )


def test_tool_calls_must_be_int():
    bad = copy.deepcopy(S.README_EXAMPLE)
    bad["tool_calls"] = "nine"
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)
    bad["tool_calls"] = [1, 2, 3]
    with pytest.raises(ValidationError):
        S.AnswerFile.model_validate(bad)


# ------------------------------------------------------------------ guard rails on the code base

PY_SOURCES = [p for d in ("agent", "graph", "mcp") for p in (ROOT / d).rglob("*.py")]
LLM_IMPORT_RE = re.compile(r"^\s*(from|import)\s+(openai|groq|anthropic|langchain\w*|litellm|llama_index|google\.generativeai)\b", re.M)


def test_no_llm_client_on_the_scoring_routing_or_graph_path():
    # P1 has no LLM anywhere; P2+ must keep agent/scoring.py and agent/policy.py clean (AGENTS.md §3).
    for p in PY_SOURCES:
        text = p.read_text(encoding="utf-8")
        assert not LLM_IMPORT_RE.search(text), f"LLM client imported in {p.relative_to(ROOT)}"


def test_the_0_65_gate_does_not_exist():
    for p in PY_SOURCES + list((ROOT / "graph" / "queries").glob("*.gsql")):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"(?<![\d.])0\.65(?![\d])", text), f"forbidden 0.65 gate in {p.relative_to(ROOT)}"


def test_policy_thresholds_present_in_transcription():
    policy = (ROOT / "data" / "regulatory" / "bank_policy.md").read_text(encoding="utf-8")
    for needle in ("0.70", "0.30", "0.85", "0.15", "$2,500", "$1,000", "$500"):
        assert needle in policy
    assert "0.65" not in policy


def test_no_hardcoded_machine_paths_or_secrets_in_sources():
    for p in PY_SOURCES:
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\Users\\|/Users/\w+/|/home/\w+/", text), p
        assert not re.search(r"gsk_[A-Za-z0-9]{10,}", text), p
        assert "tgcloud.io" not in text.replace("i.tgcloud.io)", "").replace("<workspace>.i.tgcloud.io", ""), p
