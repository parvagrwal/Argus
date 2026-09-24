"""P2 invariants in mock mode: SAR zero-out, FILE_REPORT routing, stop_reason + integer tool_calls."""

from __future__ import annotations

import copy
import csv
import json

import pytest
from pydantic import ValidationError

from agent import answer as A
from agent import policy as P
from agent.schema import AnswerFile, README_EXAMPLE
from mcp.fallback_rest import MockGraphClient

CASE_IDS = [r["case_id"] for r in csv.DictReader(open(A.L.CASE_PACK, newline="", encoding="utf-8"))]


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setenv("ARGUS_FORCE_MOCK", "1")


def test_sar_zero_out_leaks_nothing():
    for cid in ("HHG-012", "HHG-017"):
        answer, _ = A.build(cid, MockGraphClient())
        data = json.loads(answer.to_submission_json())
        if not data["sar"]["file"]:
            assert data["sar"] == {"file": False, "reason": data["sar"]["reason"], "narrative": "", "subjects": [], "total_amount_usd": 0, "activity_dates": []}
            assert "FILE_REPORT" not in json.dumps(data["next_best_actions"]["final"])
    leaky = {"file": False, "reason": "r", "narrative": "left over", "subjects": ["C1"], "total_amount_usd": 5, "activity_dates": ["2016-01-01", "2016-01-02"]}
    assert P.zero_out(leaky) == {"file": False, "reason": "r", "narrative": "", "subjects": [], "total_amount_usd": 0, "activity_dates": []}
    with pytest.raises(ValidationError):
        AnswerFile.model_validate({**README_EXAMPLE, "sar": leaky})


def test_file_report_misrouting_is_rejected():
    for exposure in (0.0, 268.43, 5_000.0):
        for rec in P.recommend(0.9, P.Flags(single_signal=False, customer_denied=True, shared_origin=True), exposure):
            if rec.action.value in ("FILE_REPORT", "BLOCK_ALL_CARDS"):
                assert rec.as_item(exposure)["route"] == "L2"
    bad = copy.deepcopy(README_EXAMPLE)
    bad["next_best_actions"]["final"][2]["route"] = "L1"  # FILE_REPORT
    with pytest.raises(ValidationError):
        AnswerFile.model_validate(bad)
    bad = copy.deepcopy(README_EXAMPLE)
    bad["next_best_actions"]["final"] = [a for a in bad["next_best_actions"]["final"] if a["action"] != "FILE_REPORT"]
    with pytest.raises(ValidationError):  # sar.file true without FILE_REPORT
        AnswerFile.model_validate(bad)


def test_stop_reason_present_and_tool_calls_int_for_every_case(tmp_path):
    for cid in CASE_IDS:
        answer, record = A.build(cid, MockGraphClient())
        data = json.loads(A.write(answer, tmp_path).read_text(encoding="utf-8"))
        assert data["stop_reason"].strip()
        assert type(data["tool_calls"]) is int and data["tool_calls"] == len(record.tool_trace) >= 1
        assert data["case"]["written_to_graph"] is False  # mock never counts as written
        assert set(data) == {"case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"}
