"""Grader v2 for Argus fraud investigation answer files.

Evaluates answer files in cases/ against frozen schema and policy rules.
Outputs scorecard under:
  - Schema&Invariants
  - Accuracy proxies
  - NBA
  - Explainability
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.schema import AnswerFile
from agent.scoring import MIN_INDEPENDENT_EVIDENCE

CASES_DIR = ROOT / "cases"
CASE_PACK = ROOT / "data" / "case_pack.csv"
CLOSED_CASES = ROOT / "data" / "closed_cases_history.csv"

# --------------------------------------------------------------------------------------
# Fraud Policy §1 & §2 Tables (transcribed verbatim)
# --------------------------------------------------------------------------------------

POLICY_ACTIONS = frozenset({
    "ALLOW_TRANSACTION",
    "DECLINE_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "BLOCK_CARD",
    "BLOCK_ALL_CARDS",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "FILE_REPORT",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD",
})

# Fraud Policy §2 — approval routing table verbatim:
# auto: ALLOW_TRANSACTION, MONITOR_CARD, MONITOR_CONNECTED_CARDS, WARN_CUSTOMER,
#       VERIFY_WITH_CUSTOMER, STEP_UP_AUTH, GENERATE_REPORT, CREATE_CASE,
#       ESCALATE_TO_ANALYST, CLOSE_NO_FRAUD
# L1 (team lead): DECLINE_TRANSACTION; BLOCK_CARD when exposure <= $2,500
# L2 (fraud manager): BLOCK_CARD when exposure > $2,500; BLOCK_ALL_CARDS always; FILE_REPORT always
AUTO_ACTIONS = frozenset({
    "ALLOW_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD",
})
L1_ACTIONS = frozenset({"DECLINE_TRANSACTION"})
L2_ACTIONS = frozenset({"BLOCK_ALL_CARDS", "FILE_REPORT"})
BLOCK_CARD_L2_THRESHOLD_USD = 2_500.00


def get_expected_route(action: str, exposure_usd: float) -> str:
    """Verbatim Fraud Policy §2 route mapping."""
    if action in AUTO_ACTIONS:
        return "auto"
    if action in L1_ACTIONS:
        return "L1"
    if action in L2_ACTIONS:
        return "L2"
    if action == "BLOCK_CARD":
        return "L2" if exposure_usd > BLOCK_CARD_L2_THRESHOLD_USD else "L1"
    return "UNKNOWN"


# Regex for rule citation in NBA reasons.
# Recognizes rule citations (R1..R10), policy sections (§3a, §6), and 3a.
RULE_CITATION_RE = re.compile(r"(R\d+|§\s*\d+[a-z]?|\b3a\b)", re.IGNORECASE)
CC_ID_RE = re.compile(r"^CC-\d+$")


def load_closed_case_ids(closed_cases_path: Path = CLOSED_CASES) -> set[str]:
    valid_ids = set()
    if not closed_cases_path.exists():
        return valid_ids
    with open(closed_cases_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("case_id"):
                valid_ids.add(row["case_id"])
    return valid_ids


def load_case_card_mapping(case_pack_path: Path = CASE_PACK) -> dict[str, str]:
    mapping = {}
    if not case_pack_path.exists():
        return mapping
    with open(case_pack_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("case_id") and row.get("card_id"):
                mapping[row["case_id"]] = row["card_id"]
    return mapping


def count_sentences(text: str) -> int:
    if not text or not text.strip():
        return 0
    matches = re.findall(r'[^.!?]+[.!?]+(?:\s+|$)', text.strip())
    return len(matches) if matches else (1 if len(text.strip()) > 0 else 0)


# --------------------------------------------------------------------------------------
# Grader Check Engine
# --------------------------------------------------------------------------------------


class CaseEvaluation:
    def __init__(self, case_id: str):
        self.case_id = case_id
        # Per category issues: list of (check_type, message)
        self.fails: dict[str, list[str]] = {
            "Schema&Invariants": [],
            "Accuracy proxies": [],
            "NBA": [],
            "Explainability": [],
        }
        self.warns: dict[str, list[str]] = {
            "Schema&Invariants": [],
            "Accuracy proxies": [],
            "NBA": [],
            "Explainability": [],
        }

    def add_fail(self, category: str, msg: str) -> None:
        self.fails[category].append(msg)

    def add_warn(self, category: str, msg: str) -> None:
        self.warns[category].append(msg)

    @property
    def total_fails(self) -> int:
        return sum(len(v) for v in self.fails.values())

    @property
    def total_warns(self) -> int:
        return sum(len(v) for v in self.warns.values())

    def status_for(self, category: str) -> str:
        if self.fails[category]:
            return f"FAIL({len(self.fails[category])})"
        if self.warns[category]:
            return f"WARN({len(self.warns[category])})"
        return "PASS"


def evaluate_single_file(file_path: Path, closed_case_ids: set[str]) -> tuple[dict[str, Any] | None, CaseEvaluation]:
    filename_stem = file_path.stem
    eval_res = CaseEvaluation(filename_stem)

    if not file_path.exists():
        eval_res.add_fail("Schema&Invariants", f"File does not exist: {file_path.name}")
        return None, eval_res

    try:
        raw_text = file_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        eval_res.add_fail("Schema&Invariants", f"Invalid JSON in {file_path.name}: {exc}")
        return None, eval_res

    # Step 0: Validate with Pydantic schema
    try:
        AnswerFile.model_validate(data)
    except Exception as exc:
        eval_res.add_fail("Schema&Invariants", f"FAIL 0 (Schema): {exc}")

    # FAIL 1: case_id != filename; stop_reason empty; tool_calls/tokens not int >= 0; latency_s not a number
    case_id = data.get("case_id", "")
    if case_id != filename_stem:
        eval_res.add_fail("Schema&Invariants", f"FAIL 1: case_id '{case_id}' != filename '{filename_stem}'")

    stop_reason = data.get("stop_reason", "")
    if not isinstance(stop_reason, str) or not stop_reason.strip():
        eval_res.add_fail("Schema&Invariants", "FAIL 1: stop_reason is empty or missing")

    tool_calls = data.get("tool_calls")
    if not isinstance(tool_calls, int) or isinstance(tool_calls, bool) or tool_calls < 0:
        eval_res.add_fail("Schema&Invariants", f"FAIL 1: tool_calls must be int >= 0, got {tool_calls!r}")

    tokens = data.get("tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        eval_res.add_fail("Schema&Invariants", f"FAIL 1: tokens must be int >= 0, got {tokens!r}")

    latency_s = data.get("latency_s")
    if not isinstance(latency_s, (int, float)) or isinstance(latency_s, bool):
        eval_res.add_fail("Schema&Invariants", f"FAIL 1: latency_s must be a number, got {latency_s!r}")

    case_obj = data.get("case", {})
    if not isinstance(case_obj, dict):
        case_obj = {}

    verdict = case_obj.get("verdict", "")
    fraud_prob = case_obj.get("fraud_probability", 0.0)
    pattern = case_obj.get("pattern", "")
    pattern_desc = case_obj.get("pattern_description", "")
    affected_txn_ids = case_obj.get("affected_txn_ids", [])
    exposure_usd = case_obj.get("exposure_usd", 0.0)
    evidence = case_obj.get("evidence", [])
    similar_priors = case_obj.get("similar_prior_cases", [])
    summary = case_obj.get("summary", "")
    written_to_graph = case_obj.get("written_to_graph", False)
    graph_case_id = case_obj.get("graph_case_id", "")
    status = case_obj.get("status", "")

    evidence_requests = data.get("evidence_requests", [])
    nba = data.get("next_best_actions", {})
    initial_actions = nba.get("initial", []) if isinstance(nba, dict) else []
    final_actions = nba.get("final", []) if isinstance(nba, dict) else []
    what_changed = nba.get("what_changed", "") if isinstance(nba, dict) else ""
    sar = data.get("sar", {}) if isinstance(data.get("sar"), dict) else {}

    # FAIL 2: NBA item: action not in Policy §1 list; route != the §2 table value for that action; reason empty or not matching rule
    for stage_name, actions_list in [("initial", initial_actions), ("final", final_actions)]:
        if not isinstance(actions_list, list):
            eval_res.add_fail("NBA", f"FAIL 2: NBA {stage_name} is not a list")
            continue
        for idx, item in enumerate(actions_list):
            if not isinstance(item, dict):
                eval_res.add_fail("NBA", f"FAIL 2: NBA {stage_name}[{idx}] is not an object")
                continue
            act = item.get("action", "")
            route = item.get("route", "")
            reason = item.get("reason", "")

            if act not in POLICY_ACTIONS:
                eval_res.add_fail("NBA", f"FAIL 2: action '{act}' in {stage_name}[{idx}] not in Policy §1 list")
            else:
                expected_route = get_expected_route(act, exposure_usd)
                if route != expected_route:
                    eval_res.add_fail(
                        "NBA",
                        f"FAIL 2: {stage_name}[{idx}] action '{act}' has route '{route}' but expected '{expected_route}'"
                    )

            if not isinstance(reason, str) or not reason.strip():
                eval_res.add_fail("NBA", f"FAIL 2: {stage_name}[{idx}] reason is empty")
            elif not RULE_CITATION_RE.search(reason):
                eval_res.add_fail(
                    "NBA",
                    f"FAIL 2: {stage_name}[{idx}] reason does not cite a policy rule/section: '{reason}'"
                )

    # FAIL 3: FILE_REPORT in final actions ⟺ sar.file == true (both directions)
    file_report_in_final = any(
        isinstance(a, dict) and a.get("action") == "FILE_REPORT" for a in final_actions
    )
    sar_file = bool(sar.get("file", False))
    if file_report_in_final != sar_file:
        eval_res.add_fail(
            "NBA",
            f"FAIL 3: FILE_REPORT in final actions ({file_report_in_final}) != sar.file ({sar_file})"
        )

    # FAIL 4: sar.file == false but narrative != "" or subjects != [] or total_amount_usd != 0 or activity_dates != []
    if not sar_file:
        narrative = sar.get("narrative", "")
        subjects = sar.get("subjects", [])
        total_amount = sar.get("total_amount_usd", 0)
        activity_dates = sar.get("activity_dates", [])
        if narrative != "" or subjects != [] or total_amount != 0 or activity_dates != []:
            eval_res.add_fail(
                "Schema&Invariants",
                f"FAIL 4: sar.file is false but fields not zeroed out: narrative={narrative!r}, subjects={subjects!r}, total={total_amount!r}, dates={activity_dates!r}"
            )

    # FAIL 5: verdict == legitimate but affected_txn_ids non-empty or exposure_usd != 0 or sar.file true
    if verdict == "legitimate":
        if affected_txn_ids:
            eval_res.add_fail("Accuracy proxies", f"FAIL 5: legitimate verdict but affected_txn_ids non-empty: {affected_txn_ids}")
        if exposure_usd != 0:
            eval_res.add_fail("Accuracy proxies", f"FAIL 5: legitimate verdict but exposure_usd != 0 ({exposure_usd})")
        if sar_file:
            eval_res.add_fail("Accuracy proxies", "FAIL 5: legitimate verdict but sar.file is true")

    # FAIL 6: verdict == fraud and len(evidence) < MIN_INDEPENDENT_EVIDENCE (Policy §6 requires at least two independent pieces of evidence); any evidence item missing claim/source/ref/entity_ids or source not in {graph, document, customer, external}
    for e_idx, e in enumerate(evidence):
        if not isinstance(e, dict):
            eval_res.add_fail("Accuracy proxies", f"FAIL 6: evidence[{e_idx}] is not an object")
            continue
        claim = e.get("claim", "")
        src = e.get("source", "")
        ref = e.get("ref", "")
        e_ids = e.get("entity_ids", None)
        if not claim or not isinstance(claim, str) or not claim.strip():
            eval_res.add_fail("Accuracy proxies", f"FAIL 6: evidence[{e_idx}] claim is empty")
        if not ref or not isinstance(ref, str) or not ref.strip():
            eval_res.add_fail("Accuracy proxies", f"FAIL 6: evidence[{e_idx}] ref is empty")
        if not isinstance(e_ids, list):
            eval_res.add_fail("Accuracy proxies", f"FAIL 6: evidence[{e_idx}] entity_ids is not a list")
        if src not in {"graph", "document", "customer", "external"}:
            eval_res.add_fail("Accuracy proxies", f"FAIL 6: evidence[{e_idx}] source '{src}' not in valid set")

    if verdict == "fraud":
        if len(evidence) < MIN_INDEPENDENT_EVIDENCE:
            eval_res.add_fail(
                "Accuracy proxies",
                f"FAIL 6: fraud verdict has {len(evidence)} evidence items (Policy §6 requires at least {MIN_INDEPENDENT_EVIDENCE} independent pieces of evidence)"
            )

    # FAIL 7: pattern == undocumented but pattern_description empty
    if pattern == "undocumented":
        if not isinstance(pattern_desc, str) or not pattern_desc.strip():
            eval_res.add_fail("Explainability", "FAIL 7: pattern is undocumented but pattern_description is empty")

    # FAIL 8: evidence_requests non-empty but what_changed == "nothing" or shorter than 20 chars
    if isinstance(evidence_requests, list) and len(evidence_requests) > 0:
        wc_str = str(what_changed).strip()
        if wc_str.lower() == "nothing" or len(wc_str) < 20:
            eval_res.add_fail(
                "Explainability",
                f"FAIL 8: evidence requested but what_changed is '{wc_str}' (length {len(wc_str)}, min 20 chars required)"
            )

    # FAIL 9: R1: fraud_probability < 0.70 AND (BLOCK_CARD or BLOCK_ALL_CARDS) in final AND neither VERIFY_WITH_CUSTOMER nor STEP_UP_AUTH in initial+final
    blocks = {"BLOCK_CARD", "BLOCK_ALL_CARDS"}
    has_block = any(isinstance(a, dict) and a.get("action") in blocks for a in final_actions)
    verifies = {"VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH"}
    has_verify = any(
        isinstance(a, dict) and a.get("action") in verifies
        for a in (initial_actions + final_actions)
    )
    if isinstance(fraud_prob, (int, float)) and fraud_prob < 0.70 and has_block and not has_verify:
        eval_res.add_fail(
            "NBA",
            f"FAIL 9 (R1): fraud_probability {fraud_prob:.2f} < 0.70 with card block in final, but no verification in initial or final"
        )

    # FAIL 10: R8: verdict == uncertain AND exposure_usd > 500 AND ESCALATE_TO_ANALYST not in final actions
    if verdict == "uncertain" and isinstance(exposure_usd, (int, float)) and exposure_usd > 500:
        has_escalate = any(isinstance(a, dict) and a.get("action") == "ESCALATE_TO_ANALYST" for a in final_actions)
        if not has_escalate:
            eval_res.add_fail(
                "NBA",
                f"FAIL 10 (R8): verdict uncertain with exposure ${exposure_usd:,.2f} > 500 but ESCALATE_TO_ANALYST not in final actions"
            )

    # FAIL 11: written_to_graph == true but graph_case_id empty
    if written_to_graph is True:
        if not isinstance(graph_case_id, str) or not graph_case_id.strip():
            eval_res.add_fail("Schema&Invariants", "FAIL 11: written_to_graph is true but graph_case_id is empty")

    # FAIL 12: similar_prior_cases entries must match ^CC-\d+$ and exist in data/closed_cases_history.csv
    if isinstance(similar_priors, list):
        for cc_id in similar_priors:
            if not isinstance(cc_id, str) or not CC_ID_RE.match(cc_id):
                eval_res.add_fail("Schema&Invariants", f"FAIL 12: similar_prior_cases entry '{cc_id}' does not match ^CC-\\d+$")
            elif closed_case_ids and cc_id not in closed_case_ids:
                eval_res.add_fail("Schema&Invariants", f"FAIL 12: similar_prior_cases entry '{cc_id}' not found in closed_cases_history.csv")

    # FAIL 13: status == open while fraud_probability >= 0.85 or <= 0.15
    if status == "open" and isinstance(fraud_prob, (int, float)):
        if fraud_prob >= 0.85 or fraud_prob <= 0.15:
            eval_res.add_fail(
                "Schema&Invariants",
                f"FAIL 13: status is 'open' while fraud_probability {fraud_prob:.2f} is in stopping band (>=0.85 or <=0.15)"
            )

    # ----------------------------------------------------------------------------------
    # WARN Checks
    # ----------------------------------------------------------------------------------

    # WARN 2: BLOCK_ALL_CARDS present (R10 needs human eyes)
    has_block_all = any(
        isinstance(a, dict) and a.get("action") == "BLOCK_ALL_CARDS"
        for a in (initial_actions + final_actions)
    )
    if has_block_all:
        eval_res.add_warn("NBA", "WARN 2: BLOCK_ALL_CARDS present (R10 needs human eyes)")

    # WARN 3: sar.file == true with no shared-device/region/ring evidence cited, exposure <= 1000, and pattern != undocumented
    if sar_file and isinstance(exposure_usd, (int, float)) and exposure_usd <= 1000 and pattern != "undocumented":
        conn_cards = case_obj.get("connected_card_ids", [])
        conn_devs = case_obj.get("connected_device_profiles", [])
        has_shared_origin = bool(conn_cards or conn_devs)
        if not has_shared_origin:
            for e in evidence:
                text_corpus = f"{e.get('claim', '')} {e.get('ref', '')}".lower()
                if any(w in text_corpus for w in ["device", "region", "ring", "shared"]):
                    has_shared_origin = True
                    break
        if not has_shared_origin:
            eval_res.add_warn(
                "Explainability",
                f"WARN 3: sar.file is true with exposure ${exposure_usd:,.2f} <= $1000, pattern '{pattern}', and no shared-origin evidence cited"
            )

    # WARN 4: summary empty or under 2 sentences
    if not isinstance(summary, str) or not summary.strip():
        eval_res.add_warn("Explainability", "WARN 4: summary is empty")
    elif count_sentences(summary) < 2:
        eval_res.add_warn("Explainability", f"WARN 4: summary is under 2 sentences (counted {count_sentences(summary)})")

    return data, eval_res


def check_cross_case_warns(all_cases: list[dict[str, Any]], evaluations: dict[str, CaseEvaluation], case_card_map: dict[str, str]) -> None:
    """WARN 1: Same card_id with verdict fraud in one case and legitimate in another."""
    card_verdicts: dict[str, set[str]] = {}
    case_card_lookup: dict[str, str] = {}

    for c in all_cases:
        cid = c.get("case_id", "")
        card_id = case_card_map.get(cid)
        v = c.get("case", {}).get("verdict")
        if card_id and v:
            case_card_lookup[cid] = card_id
            card_verdicts.setdefault(card_id, set()).add(v)

    for cid, card_id in case_card_lookup.items():
        verdicts = card_verdicts.get(card_id, set())
        if "fraud" in verdicts and "legitimate" in verdicts:
            if cid in evaluations:
                evaluations[cid].add_warn(
                    "Accuracy proxies",
                    f"WARN 1: card_id '{card_id}' has both fraud and legitimate verdicts across benchmark cases"
                )


def format_scorecard_table(evaluations: list[CaseEvaluation]) -> str:
    categories = ["Schema&Invariants", "Accuracy proxies", "NBA", "Explainability"]
    headers = ["Case ID", "Schema&Invariants", "Accuracy proxies", "NBA", "Explainability", "Overall"]
    widths = [10, 18, 18, 16, 16, 10]

    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths))
    sep_line = "-+-".join("-" * w for w in widths)

    lines = [header_line, sep_line]
    cat_counts = {c: {"PASS": 0, "FAIL": 0, "WARN": 0} for c in categories}
    total_fails = 0
    total_warns = 0

    for ev in evaluations:
        cols = [f"{ev.case_id:<{widths[0]}}"]
        for c, w in zip(categories, widths[1:5]):
            st = ev.status_for(c)
            if "FAIL" in st:
                cat_counts[c]["FAIL"] += 1
            elif "WARN" in st:
                cat_counts[c]["WARN"] += 1
            else:
                cat_counts[c]["PASS"] += 1
            cols.append(f"{st:<{w}}")

        overall = "FAIL" if ev.total_fails > 0 else ("WARN" if ev.total_warns > 0 else "PASS")
        total_fails += ev.total_fails
        total_warns += ev.total_warns
        cols.append(f"{overall:<{widths[5]}}")
        lines.append(" | ".join(cols))

    lines.append(sep_line)
    lines.append("\nSummary by Category:")
    lines.append(f"{'Category':<22} | {'PASS':<8} | {'FAIL':<8} | {'WARN':<8}")
    lines.append("-" * 52)
    for c in categories:
        lines.append(f"{c:<22} | {cat_counts[c]['PASS']:<8} | {cat_counts[c]['FAIL']:<8} | {cat_counts[c]['WARN']:<8}")
    lines.append("-" * 52)
    lines.append(f"Total Cases: {len(evaluations)} | Total Failures: {total_fails} | Total Warnings: {total_warns}")
    lines.append(f"Overall Result: {'FAIL' if total_fails > 0 else 'PASS'}")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------------------


def grade_all(cases_dir: Path = CASES_DIR) -> tuple[int, str, list[CaseEvaluation], list[dict[str, Any]]]:
    closed_case_ids = load_closed_case_ids()
    case_card_map = load_case_card_mapping()

    # Step 1: SELF-TEST on cases/HHG-017.json
    hhg017_path = cases_dir / "HHG-017.json"
    if not hhg017_path.exists():
        msg = f"Grader self-test error: reference file {hhg017_path} not found"
        print(msg)
        return 1, msg, [], []

    _, test_eval = evaluate_single_file(hhg017_path, closed_case_ids)
    if test_eval.total_fails > 0:
        err_msgs = []
        for cat, errs in test_eval.fails.items():
            for e in errs:
                err_msgs.append(f"[{cat}] {e}")
        msg = "SELF-TEST FAILED on cases/HHG-017.json:\n  " + "\n  ".join(err_msgs)
        print(msg)
        return 1, msg, [test_eval], []

    print("Step 1 SELF-TEST on cases/HHG-017.json PASSED (0 FAILs).\n")

    # Step 2: Grade all 20 cases from case_pack.csv
    case_ids = list(case_card_map.keys())
    if not case_ids:
        # Fallback to scanning cases directory
        case_ids = sorted([p.stem for p in cases_dir.glob("HHG-*.json")])

    evaluations: list[CaseEvaluation] = []
    case_data_list: list[dict[str, Any]] = []
    eval_map: dict[str, CaseEvaluation] = {}

    for cid in case_ids:
        c_path = cases_dir / f"{cid}.json"
        data, ev = evaluate_single_file(c_path, closed_case_ids)
        if data is not None:
            case_data_list.append(data)
        evaluations.append(ev)
        eval_map[cid] = ev

    # Cross-case checks
    check_cross_case_warns(case_data_list, eval_map, case_card_map)

    scorecard_str = format_scorecard_table(evaluations)
    total_fails = sum(ev.total_fails for ev in evaluations)
    exit_code = 1 if total_fails > 0 else 0

    return exit_code, scorecard_str, evaluations, case_data_list


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade Argus investigation answer files")
    parser.add_argument("--self-test-only", action="store_true", help="Run only Step 1 self-test on HHG-017.json")
    args = parser.parse_args()

    if args.self_test_only:
        closed_case_ids = load_closed_case_ids()
        hhg017_path = CASES_DIR / "HHG-017.json"
        _, test_eval = evaluate_single_file(hhg017_path, closed_case_ids)
        if test_eval.total_fails > 0:
            print("Self-test FAIL:", test_eval.fails)
            return 1
        print("Self-test PASS on HHG-017.json")
        return 0

    exit_code, scorecard_str, _, _ = grade_all()
    print(scorecard_str)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
