# Official Answer-File Specification

Extracted field-for-field from the "Answer Format" section of `data/README.md` (dataset
README, Fraud Policy v1.0). This document is the contract that `agent/schema.py` freezes.
Where this file and any planning document disagree, **the README wins**.

## File convention

- One JSON file per case, named **`<case_id>.json`**, e.g. `cases/HHG-001.json`.
- All twenty files live in a folder called **`cases/`** at the repository root.
- Same structure for every case. **Missing fields score zero for that part.**
- Every ID in the file must exist in the dataset. **Made-up IDs score zero.**
- Optional bonus investigations (autonomous monitor) go in a **separate folder** and count
  toward Innovation, not accuracy.

## Top level

| Field | Type | Required | Meaning |
|---|---|---|---|
| `case_id` | string | yes | From `case_pack.csv` |
| `case` | object | yes | Part 1 (below) |
| `evidence_requests` | list of objects | yes (may be `[]`) | Each: `type` (enum `customer_validation` \| `step_up_auth` \| `analyst_info`), `asked_after_step` (int), `assumed_response` (string). Empty if you asked for nothing |
| `next_best_actions` | object | yes | Part 3 (below) |
| `sar` | object | yes | Part 2 (below) |
| `stop_reason` | string | yes | Why the investigation ended here |
| `tool_calls` | int | yes | Graph and retrieval calls made for this case |
| `tokens` | int | yes | LLM tokens consumed for this case |
| `latency_s` | number | yes | Wall-clock seconds for this case |

## Part 1: `case`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `status` | enum `open` \| `closed_fraud` \| `closed_legitimate` \| `escalated` | yes | Where the case stands when your agent stops. `open` means more evidence is still pending |
| `verdict` | enum `fraud` \| `legitimate` \| `uncertain` | yes | Your conclusion |
| `fraud_probability` | number 0–1 | yes | How likely the flagged activity is fraud. Scored for calibration |
| `pattern` | enum (see below) | yes | The fraud pattern identified, `undocumented` if it matches none of the known ones, or `none` |
| `pattern_description` | string | yes | **Required (non-empty) when `pattern` is `undocumented`**: two or three sentences on what the pattern is, who it affects, and how you found it. Otherwise `""` |
| `affected_txn_ids` | list of strings | yes | Every transaction believed to be part of the same fraud episode, including the flagged one. **Empty if legitimate** |
| `first_suspicious_txn_id` | string or `""` | yes | Where it started |
| `connected_card_ids` | list of strings | yes | Other cards caught in the same compromise, ring, or device |
| `connected_device_profiles` | list of strings | yes | Device profiles (DeviceInfo + OS + browser + screen) linking this case to other cards |
| `exposure_usd` | number | yes | Sum of absolute amounts of `affected_txn_ids` |
| `evidence` | list of objects | yes | Each: `claim` (string), `source` (enum `graph` \| `document` \| `customer` \| `external`), `ref` (query name, document section, or request id), `entity_ids` (list of IDs the claim rests on) |
| `similar_prior_cases` | list of strings | yes (may be `[]`) | Closed-case IDs from `closed_cases_history.csv` retrieved and used as memory, e.g. `["CC-0141", "CC-2671"]` |
| `summary` | string | yes | Two to six sentences an analyst could read |
| `written_to_graph` | boolean | yes | Whether the agent stored this case in TigerGraph |
| `graph_case_id` | string or `""` | yes | The ID of the case vertex created, if any |

### `pattern` enum values

`card_testing` · `card_not_present_fraud` · `card_not_present_new_device` ·
`out_of_region_use` · `account_takeover` · `undocumented` · `none`

## Part 2: `sar`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `file` | boolean | yes | Whether a SAR should be filed. **Must agree with whether `FILE_REPORT` appears in your final actions** |
| `reason` | string | yes | Why file, or why not. Cite the policy rule |
| `narrative` | string | required when `file` is true | The report itself: who (customer, cards, merchants, devices), what happened, when (dates), where (locations, channels), how it was carried out, why it is suspicious. Six to twelve sentences |
| `subjects` | list of strings | yes | IDs of the customers, cards, merchants, and devices named in the narrative |
| `total_amount_usd` | number | yes | Total of the suspicious activity |
| `activity_dates` | list of two strings | yes | First and last date of the activity, `YYYY-MM-DD` |

**Zero-out rule (verbatim):** If `file` is false: `narrative` is `""`, `subjects` is `[]`,
`total_amount_usd` is 0, `activity_dates` is `[]`.

## Part 3: `next_best_actions`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `initial` | list of objects | yes | What you recommended **before** any requested evidence came back. Each: `action` (from the policy), `route` (enum `auto` \| `L1` \| `L2`), `reason` (cite the policy rule) |
| `final` | list of objects | yes | What you recommend **after** the assumed responses in `evidence_requests`. Same shape. **If you requested nothing, `final` equals `initial`** |
| `what_changed` | string | yes | One or two sentences on why `final` differs from `initial`, or `"nothing"` |

### `action` enum values (Fraud Policy §1, exact identifiers)

`ALLOW_TRANSACTION` · `DECLINE_TRANSACTION` · `MONITOR_CARD` · `MONITOR_CONNECTED_CARDS` ·
`WARN_CUSTOMER` · `VERIFY_WITH_CUSTOMER` · `STEP_UP_AUTH` · `BLOCK_CARD` · `BLOCK_ALL_CARDS` ·
`GENERATE_REPORT` · `CREATE_CASE` · `FILE_REPORT` · `ESCALATE_TO_ANALYST` · `CLOSE_NO_FRAUD`

Actions are ordered by what happens first.

### `route` enum values and the policy mapping (Fraud Policy §2)

| Route | Applies to |
|---|---|
| `auto` | `ALLOW_TRANSACTION`, `MONITOR_CARD`, `MONITOR_CONNECTED_CARDS`, `WARN_CUSTOMER`, `VERIFY_WITH_CUSTOMER`, `STEP_UP_AUTH`, `GENERATE_REPORT`, `CREATE_CASE`, `ESCALATE_TO_ANALYST`, `CLOSE_NO_FRAUD` |
| `L1` (team lead) | `DECLINE_TRANSACTION`; `BLOCK_CARD` when exposure ≤ $2,500 |
| `L2` (fraud manager) | `BLOCK_CARD` when exposure > $2,500; `BLOCK_ALL_CARDS` always; `FILE_REPORT` always |

## Cross-field rules stated in the README

1. `sar.file` ⟺ `FILE_REPORT` ∈ `next_best_actions.final`.
2. `sar.file == false` ⇒ `narrative == ""`, `subjects == []`, `total_amount_usd == 0`, `activity_dates == []`.
3. `verdict == legitimate` ⇒ `affected_txn_ids == []`, `exposure_usd == 0`, `sar.file == false`.
4. `pattern == undocumented` ⇒ `pattern_description` non-empty; otherwise `""`.
5. `evidence_requests == []` ⇒ `final == initial`.
6. `exposure_usd` = sum of absolute amounts of `affected_txn_ids` (Policy §4).
7. `uncertain` is a valid verdict and earns full credit on ambiguous cases, provided the
   actions follow R1 and R8.
8. `fraud_probability` should reflect what was found, not the flagged `risk_score`.
9. Customer and analyst replies are not provided: state the assumption in
   `evidence_requests` and let `final` reflect it.
10. Keep `summary` short; the evidence list carries detail; the SAR narrative is the one
    place to be complete.

## Reference example

The README's worked example is `HHG-017` (card testing, SAR filed, four final actions). It is
reproduced as the validation fixture in `agent/schema.py` (`README_EXAMPLE`).
