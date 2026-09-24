"""
FROZEN answer-file schema — P0, 2026-09-24.

Source of truth: data/README.md "Answer Format" + "Fraud Policy" (transcribed in
data/ANSWER_FORMAT.md and data/regulatory/bank_policy.md). The README wins every dispute;
differences from the Win Plan §7 are logged in data/DISCREPANCIES.md (D-01 … D-11).

Two model families live here:

* ``AnswerFile`` — exactly the README structure, ``extra="forbid"``. This is what gets
  written to ``cases/<case_id>.json``. Nothing else is allowed in that file.
* ``InternalCaseRecord`` — the plan's richer internal record (tool trace, confidence
  breakdown, stopping-rule trail, uncertainty). It wraps an ``AnswerFile`` and is used by
  the UI, the grader and the graph write-back. It is never submitted.

Cross-field rules stated in the README are enforced as validators; policy-route rules are
enforced against the Fraud Policy §2 table so a wrong route can never be serialised.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0-frozen-2026-09-24"

# --------------------------------------------------------------------------------------
# Enums (values are the exact identifiers required by the README / Fraud Policy)
# --------------------------------------------------------------------------------------


class Status(str, Enum):
    open = "open"
    closed_fraud = "closed_fraud"
    closed_legitimate = "closed_legitimate"
    escalated = "escalated"


class Verdict(str, Enum):
    fraud = "fraud"
    legitimate = "legitimate"
    uncertain = "uncertain"


class Pattern(str, Enum):
    card_testing = "card_testing"
    card_not_present_fraud = "card_not_present_fraud"
    card_not_present_new_device = "card_not_present_new_device"
    out_of_region_use = "out_of_region_use"
    account_takeover = "account_takeover"
    undocumented = "undocumented"
    none = "none"


class EvidenceSource(str, Enum):
    graph = "graph"
    document = "document"
    customer = "customer"
    external = "external"


class EvidenceRequestType(str, Enum):
    customer_validation = "customer_validation"
    step_up_auth = "step_up_auth"
    analyst_info = "analyst_info"


class Action(str, Enum):
    ALLOW_TRANSACTION = "ALLOW_TRANSACTION"
    DECLINE_TRANSACTION = "DECLINE_TRANSACTION"
    MONITOR_CARD = "MONITOR_CARD"
    MONITOR_CONNECTED_CARDS = "MONITOR_CONNECTED_CARDS"
    WARN_CUSTOMER = "WARN_CUSTOMER"
    VERIFY_WITH_CUSTOMER = "VERIFY_WITH_CUSTOMER"
    STEP_UP_AUTH = "STEP_UP_AUTH"
    BLOCK_CARD = "BLOCK_CARD"
    BLOCK_ALL_CARDS = "BLOCK_ALL_CARDS"
    GENERATE_REPORT = "GENERATE_REPORT"
    CREATE_CASE = "CREATE_CASE"
    FILE_REPORT = "FILE_REPORT"
    ESCALATE_TO_ANALYST = "ESCALATE_TO_ANALYST"
    CLOSE_NO_FRAUD = "CLOSE_NO_FRAUD"


class Route(str, Enum):
    auto = "auto"
    L1 = "L1"
    L2 = "L2"


# Fraud Policy §2 — approval routing table. BLOCK_CARD depends on exposure.
AUTO_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.ALLOW_TRANSACTION,
        Action.MONITOR_CARD,
        Action.MONITOR_CONNECTED_CARDS,
        Action.WARN_CUSTOMER,
        Action.VERIFY_WITH_CUSTOMER,
        Action.STEP_UP_AUTH,
        Action.GENERATE_REPORT,
        Action.CREATE_CASE,
        Action.ESCALATE_TO_ANALYST,
        Action.CLOSE_NO_FRAUD,
    }
)
L1_ALWAYS: frozenset[Action] = frozenset({Action.DECLINE_TRANSACTION})
L2_ALWAYS: frozenset[Action] = frozenset({Action.BLOCK_ALL_CARDS, Action.FILE_REPORT})
BLOCK_CARD_L2_THRESHOLD_USD = 2_500.00


def route_for(action: Action, exposure_usd: float) -> Route:
    """Deterministic route lookup — Fraud Policy §2. The only legal source of a route."""
    if action in AUTO_ACTIONS:
        return Route.auto
    if action in L1_ALWAYS:
        return Route.L1
    if action in L2_ALWAYS:
        return Route.L2
    if action is Action.BLOCK_CARD:
        return Route.L2 if exposure_usd > BLOCK_CARD_L2_THRESHOLD_USD else Route.L1
    raise ValueError(f"no route defined for {action!r}")  # pragma: no cover


# --------------------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False, use_enum_values=True)


class Evidence(_Strict):
    claim: str = Field(min_length=1)
    source: EvidenceSource
    ref: str = Field(min_length=1, description="query name, document section, or request id")
    entity_ids: list[str] = Field(default_factory=list)


class EvidenceRequest(_Strict):
    type: EvidenceRequestType
    asked_after_step: int = Field(ge=0)
    assumed_response: str = Field(min_length=1)


class RecommendedAction(_Strict):
    action: Action
    route: Route
    reason: str = Field(min_length=1, description="cite the policy rule")


class Case(_Strict):
    status: Status
    verdict: Verdict
    fraud_probability: float = Field(ge=0.0, le=1.0)
    pattern: Pattern
    pattern_description: str = ""
    affected_txn_ids: list[str] = Field(default_factory=list)
    first_suspicious_txn_id: str = ""
    connected_card_ids: list[str] = Field(default_factory=list)
    connected_device_profiles: list[str] = Field(default_factory=list)
    exposure_usd: float = Field(ge=0.0)
    evidence: list[Evidence] = Field(default_factory=list)
    similar_prior_cases: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    written_to_graph: bool
    graph_case_id: str = ""

    @model_validator(mode="after")
    def _readme_rules(self) -> "Case":
        if self.pattern == Pattern.undocumented.value:
            if not self.pattern_description.strip():
                raise ValueError("pattern_description is required when pattern is 'undocumented'")
        elif self.pattern_description != "":
            raise ValueError("pattern_description must be \"\" unless pattern is 'undocumented'")
        if self.verdict == Verdict.legitimate.value:
            if self.affected_txn_ids:
                raise ValueError("legitimate verdict requires affected_txn_ids == []")
            if self.exposure_usd != 0:
                raise ValueError("legitimate verdict requires exposure_usd == 0")
        if self.written_to_graph and not self.graph_case_id:
            raise ValueError("written_to_graph is true but graph_case_id is empty")
        if self.first_suspicious_txn_id and self.affected_txn_ids and (
            self.first_suspicious_txn_id not in self.affected_txn_ids
        ):
            raise ValueError("first_suspicious_txn_id must be one of affected_txn_ids")
        return self


class SAR(_Strict):
    file: bool
    reason: str = Field(min_length=1, description="why file, or why not; cite the policy rule")
    narrative: str = ""
    subjects: list[str] = Field(default_factory=list)
    total_amount_usd: float = 0.0
    activity_dates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _zero_out_or_complete(self) -> "SAR":
        if not self.file:
            # README: If `file` is false: narrative "", subjects [], total_amount_usd 0, activity_dates [].
            if self.narrative != "" or self.subjects or self.total_amount_usd != 0 or self.activity_dates:
                raise ValueError(
                    "sar.file is false: narrative must be \"\", subjects [], total_amount_usd 0, activity_dates []"
                )
            return self
        if not self.narrative.strip():
            raise ValueError("sar.narrative is required when sar.file is true")
        if len(self.activity_dates) != 2 or not all(_DATE_RE.match(d) for d in self.activity_dates):
            raise ValueError("sar.activity_dates must be exactly two YYYY-MM-DD strings when filing")
        if self.total_amount_usd <= 0:
            raise ValueError("sar.total_amount_usd must be > 0 when filing")
        return self


class NextBestActions(_Strict):
    initial: list[RecommendedAction] = Field(min_length=1)
    final: list[RecommendedAction] = Field(min_length=1)
    what_changed: str = Field(min_length=1, description='one or two sentences, or "nothing"')

    @model_validator(mode="after")
    def _what_changed_consistency(self) -> "NextBestActions":
        same = [a.model_dump() for a in self.initial] == [a.model_dump() for a in self.final]
        if same and self.what_changed.strip().lower() != "nothing":
            raise ValueError('final equals initial, so what_changed must be "nothing"')
        if not same and self.what_changed.strip().lower() == "nothing":
            raise ValueError('final differs from initial, so what_changed cannot be "nothing"')
        return self


# --------------------------------------------------------------------------------------
# The answer file — cases/<case_id>.json
# --------------------------------------------------------------------------------------

_CASE_ID_RE = re.compile(r"^HHG-\d{3}$")


class AnswerFile(_Strict):
    case_id: str
    case: Case
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    next_best_actions: NextBestActions
    sar: SAR
    stop_reason: str = Field(min_length=1)
    tool_calls: int = Field(ge=0)
    tokens: int = Field(ge=0)
    latency_s: float = Field(ge=0.0)

    @field_validator("case_id")
    @classmethod
    def _case_id_format(cls, v: str) -> str:
        if not _CASE_ID_RE.match(v):
            raise ValueError("case_id must look like HHG-001 (from case_pack.csv)")
        return v

    @model_validator(mode="after")
    def _cross_part_rules(self) -> "AnswerFile":
        final_actions = {a.action for a in self.next_best_actions.final}

        # README: sar.file must agree with whether FILE_REPORT appears in final actions.
        if self.sar.file != (Action.FILE_REPORT.value in final_actions):
            raise ValueError("sar.file must equal (FILE_REPORT in next_best_actions.final)")

        # README: legitimate verdict => sar.file false.
        if self.case.verdict == Verdict.legitimate.value and self.sar.file:
            raise ValueError("legitimate verdict requires sar.file == false")

        # README: if you requested nothing, final equals initial.
        if not self.evidence_requests:
            ini = [a.model_dump() for a in self.next_best_actions.initial]
            fin = [a.model_dump() for a in self.next_best_actions.final]
            if ini != fin:
                raise ValueError("evidence_requests is empty, so final must equal initial")

        # Fraud Policy §2: routes are a deterministic function of (action, exposure).
        for stage in ("initial", "final"):
            for item in getattr(self.next_best_actions, stage):
                expected = route_for(Action(item.action), self.case.exposure_usd)
                if item.route != expected.value:
                    raise ValueError(
                        f"{stage}: {item.action} at exposure {self.case.exposure_usd:.2f} must route "
                        f"{expected.value}, got {item.route}"
                    )

        # Fraud Policy 3a: a report always has a case behind it.
        if self.sar.file and Action.CREATE_CASE.value not in final_actions:
            raise ValueError("FILE_REPORT requires CREATE_CASE in final actions (policy 3a)")

        # Policy §4 / README: sar total should not exceed identified exposure by more than rounding.
        if self.sar.file and self.sar.total_amount_usd > self.case.exposure_usd + 0.01:
            raise ValueError("sar.total_amount_usd cannot exceed case.exposure_usd")
        return self

    def to_submission_json(self) -> str:
        """Serialise exactly the README structure, stable key order, 2-space indent."""
        import json

        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------
# Internal record (Win Plan §7 extras) — NOT part of the submitted file
# --------------------------------------------------------------------------------------


class ToolCall(_Strict):
    step: int = Field(ge=0)
    agent: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    rows: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    ts: str


class ConfidenceBreakdown(_Strict):
    """Per-feature contributions from the deterministic scorer (agent/scoring.py)."""

    features: dict[str, float]
    weights: dict[str, float]
    bias: float
    logit: float
    probability: float = Field(ge=0.0, le=1.0)
    cold_start_capped: bool = False


class StoppingDecision(_Strict):
    round: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)
    independent_evidence: int = Field(ge=0)
    rule_fired: str
    continue_investigating: bool
    note: str = ""


class InternalCaseRecord(_Strict):
    """Everything the UI/grader needs beyond the README file. Never written to cases/."""

    schema_version: str = SCHEMA_VERSION
    answer: AnswerFile
    trigger_type: str
    trigger_text: str
    opened_at: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    flagged_risk_score: float | None = None
    tool_trace: list[ToolCall] = Field(default_factory=list)
    confidence_breakdown: ConfidenceBreakdown | None = None
    decisions: list[StoppingDecision] = Field(default_factory=list)
    uncertainty: str = ""
    simulated_evidence: bool = True

    @model_validator(mode="after")
    def _trace_matches_count(self) -> "InternalCaseRecord":
        if self.tool_trace and len(self.tool_trace) != self.answer.tool_calls:
            raise ValueError("answer.tool_calls must equal len(tool_trace)")
        return self


# --------------------------------------------------------------------------------------
# README worked example — used as the validation fixture (python -m agent.schema)
# --------------------------------------------------------------------------------------

README_EXAMPLE: dict[str, Any] = {
    "case_id": "HHG-017",
    "case": {
        "status": "closed_fraud",
        "verdict": "fraud",
        "fraud_probability": 0.86,
        "pattern": "card_testing",
        "pattern_description": "",
        "affected_txn_ids": ["T0412877", "T0412878", "T0412879", "T0412883"],
        "first_suspicious_txn_id": "T0412877",
        "connected_card_ids": ["C00877-K1"],
        "connected_device_profiles": [
            "SAMSUNG SM-G892A Build/NRD90M | Android 7.0 | samsung browser 6.2 | 2220x1080"
        ],
        "exposure_usd": 268.43,
        "evidence": [
            {
                "claim": "Three online authorizations under $3 within 40 minutes, then a $259 purchase under a product code this card has never used",
                "source": "graph",
                "ref": "query:card_window(card_id=C00377-K1, hours=2)",
                "entity_ids": ["T0412877", "T0412878", "T0412879", "T0412883"],
            },
            {
                "claim": "All four came from a device profile marked New for this account (Android 7.0, Chrome for Android, 1920x1080), seen on closed case CC-0141 and on card C00877-K1 this month",
                "source": "graph",
                "ref": "query:device_neighbors(device_id=D000731)",
                "entity_ids": ["CC-0141", "C00877-K1"],
            },
            {
                "claim": "Customer denied the purchases when asked",
                "source": "customer",
                "ref": "evidence_request:1",
                "entity_ids": [],
            },
        ],
        "similar_prior_cases": ["CC-0141"],
        "summary": "Textbook card testing: three sub-$3 online authorizations in 40 minutes, then a $259 purchase in a category the cardholder has never used. All four share a device profile marked New for this account, which appears on a closed case from August and on another card this month. Customer denied the activity. Card compromised; a second card is likely compromised through the same device.",
        "written_to_graph": True,
        "graph_case_id": "CASE-2016-1187",
    },
    "evidence_requests": [
        {
            "type": "customer_validation",
            "asked_after_step": 4,
            "assumed_response": "Customer states they did not make these purchases and still has the card",
        }
    ],
    "next_best_actions": {
        "initial": [
            {"action": "DECLINE_TRANSACTION", "route": "L1", "reason": "R5: testing sequence observed, purchase already cleared"},
            {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: probability 0.72 on pattern alone, confirm before blocking"},
        ],
        "final": [
            {"action": "BLOCK_CARD", "route": "L1", "reason": "R2 and R5: customer denied; exposure $268 is under $2,500"},
            {"action": "CREATE_CASE", "route": "auto", "reason": "R2"},
            {"action": "FILE_REPORT", "route": "L2", "reason": "R2: shared device links this to another compromised card"},
            {"action": "MONITOR_CONNECTED_CARDS", "route": "auto", "reason": "Same device profile also used on C00877-K1"},
        ],
        "what_changed": "Customer denial raised probability from 0.72 to 0.86 and confirmed the block. The shared device profile with C00877-K1 triggers a report and monitoring of the connected card.",
    },
    "sar": {
        "file": True,
        "reason": "R2: confirmed unauthorized use linked by a shared device to a second compromised card",
        "narrative": "On 2016-11-14 between 09:12 and 09:52, card C00377-K1 belonging to customer C00377 was used for three online authorizations of $1.10, $2.40, and $0.95 followed at 10:31 by a $259.98 online purchase under a product code the cardholder had never used. All four transactions came from a device profile marked New for this account, previously recorded on closed case CC-0141 (confirmed fraud, August 2016) and on card C00877-K1 on 2016-11-12. The cardholder, contacted the same day, stated they did not make these purchases and remained in possession of the card. The sequence of small authorizations followed by a larger purchase is consistent with testing of a stolen card number prior to use. The shared device indicates a common actor across at least two cardholders. Total unauthorized amount: $268.43. Card blocked and scheduled for reissue; card C00877-K1 placed under monitoring.",
        "subjects": ["C00377", "C00377-K1", "C00877-K1"],
        "total_amount_usd": 268.43,
        "activity_dates": ["2016-11-14", "2016-11-14"],
    },
    "stop_reason": "Customer denial settled the verdict; device link identified and connected card protected. Further steps would not change the actions.",
    "tool_calls": 9,
    "tokens": 12480,
    "latency_s": 18.7,
}

MINIMAL_LEGITIMATE_EXAMPLE: dict[str, Any] = {
    "case_id": "HHG-012",
    "case": {
        "status": "closed_legitimate",
        "verdict": "legitimate",
        "fraud_probability": 0.08,
        "pattern": "none",
        "pattern_description": "",
        "affected_txn_ids": [],
        "first_suspicious_txn_id": "",
        "connected_card_ids": [],
        "connected_device_profiles": [],
        "exposure_usd": 0,
        "evidence": [
            {
                "claim": "Card has prior in-person history in billing region 494.0 while home activity continued",
                "source": "graph",
                "ref": "query:region_profile(card_id=C05876-K2)",
                "entity_ids": ["C05876-K2"],
            },
            {
                "claim": "Closed case CC-0003 cleared a 0.91-scored alert on this card after the cardholder confirmed travel",
                "source": "graph",
                "ref": "query:similar_prior_cases(card_id=C05876-K2)",
                "entity_ids": ["CC-0003"],
            },
        ],
        "similar_prior_cases": ["CC-0003"],
        "summary": "In-person $30.91 purchase in a region the card has visited before; home-region activity continued. Prior alert on the same card was cleared as travel. Legitimate.",
        "written_to_graph": False,
        "graph_case_id": "",
    },
    "evidence_requests": [],
    "next_best_actions": {
        "initial": [{"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3-equivalent: travel history exonerates; single weak signal"}],
        "final": [{"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3-equivalent: travel history exonerates; single weak signal"}],
        "what_changed": "nothing",
    },
    "sar": {"file": False, "reason": "Not fraud; policy 3a conditions not met", "narrative": "", "subjects": [], "total_amount_usd": 0, "activity_dates": []},
    "stop_reason": "Probability 0.08 with two independent pieces of evidence; policy §6 stop condition met.",
    "tool_calls": 3,
    "tokens": 2100,
    "latency_s": 4.2,
}


def _selftest() -> None:
    a = AnswerFile.model_validate(README_EXAMPLE)
    b = AnswerFile.model_validate(MINIMAL_LEGITIMATE_EXAMPLE)
    # round-trip
    assert AnswerFile.model_validate_json(a.to_submission_json()) == a
    assert AnswerFile.model_validate_json(b.to_submission_json()) == b
    # negative checks: wrong route, leaky SAR, sar/FILE_REPORT disagreement
    import copy

    bad = copy.deepcopy(README_EXAMPLE)
    bad["next_best_actions"]["final"][2]["route"] = "L1"
    try:
        AnswerFile.model_validate(bad)
        raise AssertionError("wrong FILE_REPORT route accepted")
    except ValueError:
        pass
    bad = copy.deepcopy(MINIMAL_LEGITIMATE_EXAMPLE)
    bad["sar"]["narrative"] = "leftover"
    try:
        AnswerFile.model_validate(bad)
        raise AssertionError("SAR zero-out violation accepted")
    except ValueError:
        pass
    bad = copy.deepcopy(README_EXAMPLE)
    bad["sar"]["file"] = False
    bad["sar"].update(narrative="", subjects=[], total_amount_usd=0, activity_dates=[])
    try:
        AnswerFile.model_validate(bad)
        raise AssertionError("sar.file/FILE_REPORT disagreement accepted")
    except ValueError:
        pass
    print(f"agent/schema.py {SCHEMA_VERSION}: README example + minimal legitimate example validate; "
          "3 negative checks rejected as expected.")


if __name__ == "__main__":
    _selftest()
