# AGENTS.md — Operating Constraints for Argus

Argus is an agentic fraud-investigation system built on TigerGraph for Hacker House Goa 2026.
These rules bind every contributor and every AI coding assistant working in this repository.
They exist to stop the one failure mode judges punish hardest: an agent costume over a script.
Violations are build-breaking, not style nits.

## 1. Real graph, real evidence

- Every investigation step calls **real TigerGraph tools** (MCP tools or the documented
  REST++ fallback that implements the same interface). No mocked graph nodes. No synthetic
  evidence. No hardcoded query results.
- Every `evidence` item in an answer file must trace to an actual tool call recorded in the
  internal `tool_trace`, a retrieved document chunk, or a recorded (simulated) evidence request.
- Offline/demo fixtures are **recorded outputs of real queries**, labelled as fixtures, and
  never used to generate answer files that are submitted as investigations.
- Every ID in an answer file must exist in the dataset. Fabricated IDs score zero and are a bug.

## 2. Confidence is computed, never asserted

- `case.fraud_probability` is produced by **deterministic code** in `agent/scoring.py` from
  graph outputs and evidence features. It is never a constant, never hand-tuned per case, and
  **never an LLM output**.
- Weights are fit on `closed_cases_history.csv`; the formula, weights and calibration are
  documented so a judge can recompute any case by hand.
- Cold-start accounts (no history in the graph) are capped below the action threshold.

## 3. The LLM narrates; it does not decide

- The LLM **reasons, selects tools, synthesises and explains**. It writes `summary`,
  `sar.narrative`, `reason` strings, `pattern_description` and `stop_reason` prose.
- The LLM **never** computes scores, exposure, approval routes, or pattern labels. Pattern
  classification and routing are deterministic functions of graph outputs and the policy.
- No LLM client may be imported in `agent/scoring.py`, `agent/policy.py`, or any module on
  the scoring/routing path. A test enforces this.
- Every factual claim the LLM writes must cite an evidence item or an ID that exists.
  Uncited claims are a build failure. If retrieval returns nothing, the agent says so.

## 4. Approval routes come only from the policy engine

- `route` values (`auto` / `L1` / `L2`) are assigned exclusively by the deterministic policy
  engine (`agent/policy.py`) implementing Fraud Policy §2 as transcribed verbatim in
  `data/regulatory/bank_policy.md`.
- Hard locks: `FILE_REPORT` → `L2` always; `BLOCK_ALL_CARDS` → `L2` always;
  `DECLINE_TRANSACTION` → `L1`; `BLOCK_CARD` → `L1` when exposure ≤ $2,500, `L2` above.
- Only `auto` actions may be executed by the agent. `L1`/`L2` actions are recommended with
  the route stated and wait for a human.
- Any policy mismatch discovered later is fixed in the transcription first, never silently
  in code.

## 5. Next best actions must visibly evolve

- Every case records `next_best_actions.initial` → `evidence_requests` →
  `next_best_actions.final` + `what_changed`.
- If evidence was requested, `final` must reflect the assumed response and `what_changed`
  must explain the difference in one or two sentences. If nothing was requested, `final`
  equals `initial` and `what_changed` is exactly `"nothing"`.
- A fake `what_changed` on a case with evidence requests is a build failure.
- Simulated customer/analyst responses are seeded per case, labelled as simulated, and the
  assumption is written in `evidence_requests[].assumed_response`.

## 6. SAR discipline

- `sar.file` is `true` **iff** `FILE_REPORT` appears in `next_best_actions.final`.
- If `sar.file` is `false`: `narrative = ""`, `subjects = []`, `total_amount_usd = 0`,
  `activity_dates = []`. No leftovers. A post-processor enforces it and a test byte-checks it.
- If `sar.file` is `true`: the narrative stands on its own (who, what, when, where, how, why),
  six to twelve sentences, every entity it names is in `subjects`, and a `CREATE_CASE`
  backs it (policy 3a).

## 7. Schema is frozen

- `agent/schema.py` is the frozen contract from `data/ANSWER_FORMAT.md`. The README wins
  every dispute. Changing the schema requires an entry in `data/DISCREPANCIES.md` citing the
  README passage that justifies it.
- Answer files are exactly `cases/<case_id>.json`, validate against `AnswerFile`, and contain
  no extra keys. Internal detail lives in `InternalCaseRecord`, never in the submitted file.
- A legitimate verdict means `affected_txn_ids = []`, `exposure_usd = 0`, `sar.file = false`.
  Legitimate cases are cleared **with the exonerating evidence named**.

## 8. Memory is bi-directional and verified

- Every investigated case is written to the graph and read back; the answer file is emitted
  only after read-back equality is asserted, and `graph_case_id` is the real vertex ID.
- Later cases retrieve and cite earlier ones in `similar_prior_cases`. Write-only memory is
  a defect.

## 9. Honesty about the data

- The V, C, D, M and numeric `id_` columns are unnamed model features. Evidence may use them
  as signals but must say so; never pretend to know what `V127` means.
- The `risk_score` is an input, never a verdict. Half the cases are legitimate; an agent that
  blocks everything is wrong.
- Never use the public IEEE-CIS/Kaggle files to recover outcomes. That is disqualification.

## 10. Repository hygiene

- Secrets live in `.env` (never committed); `.env.example` documents every variable.
- `transactions.csv` and `identity.csv` are not committed (size); `case_pack.csv` and
  `closed_cases_history.csv` are.
- No hardcoded usernames or machine paths. Clone-and-run instructions are tested from a
  fresh checkout. Commit messages describe what changed and why.
