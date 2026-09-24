"""Deterministic policy engine: Fraud Policy v1.0 §1-§7 as decision tables. No LLM here."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agent.schema import Action, EvidenceRequestType, Route, Status, Verdict, route_for

# Threshold index from data/regulatory/bank_policy.md
R1_VERIFY_FIRST = 0.70
OPEN_CASE = 0.30
STOP_HIGH, STOP_LOW = 0.85, 0.15
SAR_EXPOSURE = 1_000.0
ESCALATE_EXPOSURE = 500.0
R5_CLEARED_PURCHASE = 100.0


@dataclass
class Flags:
    """Evidence flags the policy reads. Set by loop.py from scoring.Features, never by prose."""

    single_signal: bool = True
    customer_denied: bool = False
    customer_confirmed: bool = False
    no_reply: bool = False
    card_testing: bool = False
    cleared_purchase_over_100: bool = False
    shared_origin: bool = False        # same device profile / region cluster / recipient email
    recurring_match: bool = False      # R7 approximation (same amount, product, ~monthly)
    undocumented: bool = False
    multi_card_confirmed_fraud: bool = False
    evidence_conflict: bool = False
    cold_start: bool = False
    independent_evidence: int = 0


@dataclass
class Rec:
    action: Action
    reason: str

    def as_item(self, exposure: float) -> dict[str, str]:
        return {"action": self.action.value, "route": route_for(self.action, exposure).value, "reason": self.reason}


def verdict_for(p: float, f: Flags) -> tuple[str, str]:
    """(verdict, status). `uncertain` is legitimate output on ambiguous cases (README note)."""
    if f.customer_confirmed and not f.evidence_conflict:
        return Verdict.legitimate.value, Status.closed_legitimate.value
    if p >= R1_VERIFY_FIRST or f.customer_denied:
        return Verdict.fraud.value, Status.closed_fraud.value
    if p <= OPEN_CASE and not f.evidence_conflict:
        return Verdict.legitimate.value, Status.closed_legitimate.value
    return Verdict.uncertain.value, Status.escalated.value if f.evidence_conflict else Status.open.value


def sar_conditions(p: float, f: Flags, exposure: float) -> list[str]:
    """Policy 3a: confirmed or strongly suspected AND at least one trigger. Returns the triggers met."""
    strong = p >= R1_VERIFY_FIRST or f.customer_denied
    if not strong or exposure <= 0:  # nothing identified in the graph -> nothing to report
        return []
    hits = []
    if exposure > SAR_EXPOSURE:
        hits.append(f"exposure ${exposure:,.2f} exceeds $1,000 (3a)")
    if f.shared_origin:
        hits.append("activity connects to a shared device profile or another customer's fraud (3a, R6)")
    if f.undocumented:
        hits.append("pattern is coordinated or undocumented (3a, R9)")
    return hits


def recommend(p: float, f: Flags, exposure: float) -> list[Rec]:
    """Decision table -> ordered actions (what happens first, first). Reasons cite rule numbers."""
    recs: list[Rec] = []
    verdict, _ = verdict_for(p, f)

    if f.customer_confirmed and not f.evidence_conflict:
        if f.recurring_match:
            return [Rec(Action.CREATE_CASE, "R7: disputed charge matches the cardholder's own recurring pattern"),
                    Rec(Action.WARN_CUSTOMER, "R7: recurring charge reminder"),
                    Rec(Action.CLOSE_NO_FRAUD, "R3: customer confirmed the transaction")]
        return [Rec(Action.CLOSE_NO_FRAUD, "R3: customer confirmed the transaction; confirmation noted in the case file")]

    if f.card_testing:
        recs.append(Rec(Action.DECLINE_TRANSACTION, "R5: testing sequence observed; decline pending authorizations"))
        recs.append(Rec(Action.STEP_UP_AUTH, "R5: require step-up before further activity"))

    if verdict == Verdict.legitimate.value:
        recs.append(Rec(Action.CLOSE_NO_FRAUD, f"probability {p:.2f} at or below the 0.30 case threshold with exonerating evidence (§3a, §6)"))
        return recs

    if f.customer_denied:
        recs.append(Rec(Action.BLOCK_CARD, f"R2: customer denied the transaction; exposure ${exposure:,.2f}"))
        recs.append(Rec(Action.CREATE_CASE, "R2: customer denied; internal case with the evidence attached (3a)"))
    elif f.card_testing and f.cleared_purchase_over_100:
        recs.append(Rec(Action.BLOCK_CARD, "R5: a purchase over $100 has already cleared after the testing sequence"))
        recs.append(Rec(Action.CREATE_CASE, "3a: probability at or above 0.30"))
    elif p >= R1_VERIFY_FIRST and not f.single_signal:
        recs.append(Rec(Action.BLOCK_CARD, f"probability {p:.2f} >= 0.70 on more than one independent signal (R1 satisfied)"))
        recs.append(Rec(Action.CREATE_CASE, "3a: probability at or above 0.30"))
    else:
        recs.append(Rec(Action.VERIFY_WITH_CUSTOMER if not f.no_reply else Action.MONITOR_CARD,
                        f"R1: probability {p:.2f} rests on a single signal or is below 0.70; verify before any block" if not f.no_reply
                        else "R4: no reply within 24 hours; raise monitoring"))
        if f.no_reply:
            recs.append(Rec(Action.DECLINE_TRANSACTION, "R4: decline pending authorizations while unanswered"))
        recs.append(Rec(Action.CREATE_CASE, "3a: probability at or above 0.30 / evidence requested / customer dispute"))

    if f.multi_card_confirmed_fraud:
        recs.append(Rec(Action.BLOCK_ALL_CARDS, "R10: at least two of the customer's cards show confirmed fraud"))
    for hit in sar_conditions(p, f, exposure)[:1]:
        recs.append(Rec(Action.FILE_REPORT, f"3a: {hit}"))
    if f.shared_origin:
        recs.append(Rec(Action.MONITOR_CONNECTED_CARDS, "R6: cards sharing the device profile / region cluster / recipient email"))
    if f.undocumented:
        recs.append(Rec(Action.ESCALATE_TO_ANALYST, "R9: undocumented pattern described in own words; analyst review"))
    elif verdict == Verdict.uncertain.value and (exposure > ESCALATE_EXPOSURE or f.evidence_conflict):
        recs.append(Rec(Action.ESCALATE_TO_ANALYST, f"R8: verdict uncertain with exposure ${exposure:,.2f} > $500 or conflicting evidence"))
    if f.no_reply and exposure > ESCALATE_EXPOSURE and not any(r.action is Action.ESCALATE_TO_ANALYST for r in recs):
        recs.append(Rec(Action.ESCALATE_TO_ANALYST, "R4: no reply and exposure exceeds $500"))
    return recs


# ---------------------------------------------------------------- evidence requests by expected value

# Customer impact from Policy §1 mapped to a cost in "case value" units (High=block is not an evidence action).
ACTION_COST = {EvidenceRequestType.customer_validation: 0.10, EvidenceRequestType.step_up_auth: 0.12,
               EvidenceRequestType.analyst_info: 0.25}


def p_information_gain(req: EvidenceRequestType, p: float, f: Flags) -> float:
    """Chance the response settles the question: highest when p is mid-range; analysts help when evidence conflicts."""
    uncertainty = 1.0 - abs(2 * p - 1)  # 1 at p=0.5, 0 at the extremes
    base = {EvidenceRequestType.customer_validation: 0.9, EvidenceRequestType.step_up_auth: 0.6,
            EvidenceRequestType.analyst_info: 0.5 + 0.4 * f.evidence_conflict}[req]
    if f.no_reply and req is EvidenceRequestType.customer_validation:
        base = 0.1
    return round(base * uncertainty, 4)


def case_value(p: float, exposure: float) -> float:
    """Value of getting the decision right: exposure at risk plus the fixed cost of a wrong block/clear."""
    return min(1.0, exposure / SAR_EXPOSURE) * 0.5 + 0.5


def rank_evidence_requests(p: float, f: Flags, exposure: float) -> list[tuple[EvidenceRequestType, float]]:
    """EV = P(information gain) x case value - action cost; only positive EV requests are worth asking."""
    ranked = []
    for req in EvidenceRequestType:
        ev = p_information_gain(req, p, f) * case_value(p, exposure) - ACTION_COST[req]
        ranked.append((req, round(ev, 4)))
    ranked.sort(key=lambda t: -t[1])
    return [(r, ev) for r, ev in ranked if ev > 0]


def should_request_evidence(p: float, f: Flags) -> bool:
    """§6: stop when settled. R1: verify first on a weak signal. Otherwise ask only in the uncertain band."""
    if f.customer_denied or f.customer_confirmed or f.no_reply:
        return False
    if p >= STOP_HIGH and f.independent_evidence >= 2:
        return False
    if p <= STOP_LOW and f.independent_evidence >= 2:
        return False
    return OPEN_CASE <= p < STOP_HIGH or f.evidence_conflict


def simulate_response(case_id: str, req: EvidenceRequestType, p: float) -> tuple[str, str]:
    """Seeded per case (AGENTS.md §5): the cardholder denies with probability p. Returns (outcome, text)."""
    seed = int(hashlib.sha256(f"{case_id}:{req.value}".encode()).hexdigest(), 16) % 10_000 / 10_000
    if req is EvidenceRequestType.analyst_info:
        return "analyst", "SIMULATED analyst reply: prior cases on this card re-checked; no additional context beyond the graph record"
    if seed < p:
        return "denied", f"SIMULATED cardholder reply ({req.value}): 'I did not make this transaction and I still have the card.'"
    return "confirmed", f"SIMULATED cardholder reply ({req.value}): 'Yes, that purchase was mine.'"


# ---------------------------------------------------------------- SAR assembly and zero-out


def sar_fields(final: list[dict[str, str]], p: float, f: Flags, exposure: float, draft: dict) -> dict:
    """sar.file iff FILE_REPORT in final; otherwise the README zero-out applies to every SAR field."""
    file_it = any(a["action"] == Action.FILE_REPORT.value for a in final)
    if not file_it:
        hits = sar_conditions(p, f, exposure)
        why = ("3a: fraud not confirmed or strongly suspected" if not (p >= R1_VERIFY_FIRST or f.customer_denied)
               else "3a: none of the report triggers holds (exposure <= $1,000, no shared origin, documented pattern)")
        return zero_out({"file": False, "reason": why if not hits else "3a: report conditions noted but FILE_REPORT not in final actions"})
    return {"file": True, "reason": "3a/R2: " + "; ".join(sar_conditions(p, f, exposure)) or "3a", "narrative": draft.get("narrative", ""),
            "subjects": draft.get("subjects", []), "total_amount_usd": round(exposure, 2), "activity_dates": draft.get("activity_dates", [])}


def zero_out(sar: dict) -> dict:
    """README: file false => narrative "", subjects [], total 0, dates []. Applied to any SAR dict."""
    if sar.get("file"):
        return sar
    return {"file": False, "reason": sar.get("reason", "3a: conditions not met"), "narrative": "", "subjects": [],
            "total_amount_usd": 0, "activity_dates": []}


def what_changed(initial: list[dict], final: list[dict], response: str) -> str:
    if initial == final:  # schema compares full items, reasons included
        return "nothing"
    return (f"The simulated evidence response ({response}) changed the recommendation from "
            f"{', '.join(a['action'] for a in initial)} to {', '.join(a['action'] for a in final)}.")
