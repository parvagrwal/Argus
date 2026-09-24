# Win Plan v2.0 — Verification Log (P0 Day-0 audit)

Audited 2026-09-24 against `data/README.md`, `case_pack.csv`, `closed_cases_history.csv`,
`identity.csv` and `transactions.csv`. Convention: **the README wins every dispute.**
Each entry states the plan's claim, what the data says, and the correction the team adopts.

**Total discrepancies logged: 18** (D-01 … D-18). Verified-correct claims are listed at the end.

---

## A. Answer-file schema — plan §7 vs README "Answer Format"

The plan's §7 "expected shape" was written before the README was read and is materially
different. `agent/schema.py` is frozen to the README; the plan's internal-only fields are kept
in a separate `InternalCaseRecord` model that is **never** written into `cases/<id>.json`.

| # | Plan §7 says | README says | Correction |
|---|---|---|---|
| D-01 | Top-level keys `case, investigation_record, evidence, findings, confidence_score, confidence_breakdown, similar_prior_cases, evidence_requests, next_best_actions, sar, decisions, case_summary, graph_case_id, uncertainty` | Top-level keys are exactly `case_id, case, evidence_requests, next_best_actions, sar, stop_reason, tool_calls, tokens, latency_s` | Use README keys. `evidence`, `similar_prior_cases`, `summary`, `graph_case_id`, `written_to_graph` live **inside `case`**. `investigation_record`, `findings`, `confidence_breakdown`, `decisions`, `uncertainty`, `case_summary` are not answer-file fields |
| D-02 | `case` carries `id, trigger, opened_at, card_id, customer_id, flagged_transaction, exposure_usd` | `case` carries `status, verdict, fraud_probability, pattern, pattern_description, affected_txn_ids, first_suspicious_txn_id, connected_card_ids, connected_device_profiles, exposure_usd, evidence, similar_prior_cases, summary, written_to_graph, graph_case_id` | Trigger metadata is not part of the answer; only `case_id` (top level) identifies the case |
| D-03 | `confidence_score` (float) | `case.fraud_probability` (number 0–1, "scored for calibration") | Rename. Internally the deterministic score feeds `fraud_probability` |
| D-04 | `findings.pattern` ∈ five patterns \| `undocumented` \| `legitimate` | `case.pattern` ∈ `card_testing, card_not_present_fraud, card_not_present_new_device, out_of_region_use, account_takeover, undocumented, none` | Enum value is **`none`**, not `legitimate`. `legitimate` is a `verdict` value |
| D-05 | Evidence items `{id: "E1", type, source, content, supports}` | `{claim, source (graph\|document\|customer\|external), ref, entity_ids}` | Use README shape. `E1…En` IDs may be used in `ref`/summary prose but are not a field |
| D-06 | NBA items have `action, route, rationale` | NBA items have `action, route, reason` | Field is **`reason`** |
| D-07 | `sar: {file, narrative, subjects[], total_amount_usd, activity_dates[]}` | Also requires **`reason`** (why file or why not, citing the rule) | Add `sar.reason` |
| D-08 | `tool_trace` embedded in the answer file (I1, T10) | README has `tool_calls` (int), `tokens` (int), `latency_s` (number); no trace structure | Keep the full trace in `InternalCaseRecord` / UI; emit only the count in the answer file. README says "Same structure for every case" — do not add unknown keys |
| D-09 | `decisions` (stopping-rule trail with EV numbers) | `stop_reason` (string) | Summarise the trail into `stop_reason`; keep numbers internal |
| D-10 | `evidence_requests`: "what was asked, via which simulated action, what came back" | Each item is exactly `type (customer_validation\|step_up_auth\|analyst_info), asked_after_step (int), assumed_response (string)` | Use README shape |
| D-11 | §9.3 example action `REQUEST_EVIDENCE` | No such action in the policy. Evidence gathering is `VERIFY_WITH_CUSTOMER` / `STEP_UP_AUTH` / `ESCALATE_TO_ANALYST` | Never emit `REQUEST_EVIDENCE` |

Additional README rules the plan does not mention, now enforced by the schema:
`status` enum (`open|closed_fraud|closed_legitimate|escalated`); `first_suspicious_txn_id`;
`connected_device_profiles`; `written_to_graph`; `activity_dates` must be exactly two
`YYYY-MM-DD` strings when filing; "If you requested nothing, `final` equals `initial`".

## B. Thresholds and architecture

| # | Plan claim | Data / README | Correction |
|---|---|---|---|
| D-12 | §6.5/§6.6 gates: conf ≥ 0.85 → act, conf < 0.65 → gather evidence | Policy R1 threshold is **0.70** (verify before block below 0.70); case opens at **0.30**; stop at **≥ 0.85 or ≤ 0.15 with ≥ 2 independent pieces of evidence** | Policy engine uses 0.70 / 0.30 / 0.85 / 0.15. The 0.65 figure is not in the policy |
| D-13 | §6.1 graph schema: vertices `Device, IP, Merchant`; edges `USES_IP`, `SIMILAR_TO`, `FLAGGED_BY`; vector attribute on `Transaction` | The data has **no IP address and no merchant identifier** anywhere. README suggests `Customer, Card, Transaction, DeviceProfile (DeviceInfo+OS+browser+screen), EmailDomain, BillingRegion, ClosedCase` | Drop `IP`/`Merchant` vertices; add `EmailDomain`, `BillingRegion`, `ClosedCase`. "Same recipient email" (R6) maps to `R_emaildomain` |
| D-14 | T1 innocence test: "recurring-subscription match" (R7) | R7 exists, but there is no merchant column, and **zero** closed-case notes mention "recurring" or "subscription". Cleared-case reasons in history are only: confirmed travel (716), new phone (158), unusual-but-intended amount (26) | Innocence tests must be built on: travel/region history, device-added-to-profile history, customer confirmation. R7 can only be approximated via same-`TransactionAmt` + same `ProductCD` + ~monthly cadence on the same card |
| D-15 | `card_id` is loadable from the transaction file | `transactions.csv` has **no `card_id` column**; only `card1…card6` + `customer_id`. README: card IDs are "derived from the card issuer field; one customer can have several cards" | P1 must derive `Cxxxxx-Kn` per customer and validate the derivation against the `card_id` values in `closed_cases_history.csv` before loading |

## C. Battle table (plan §8) — per-case verification

Every row's ID, trigger, risk score, flagged transaction, amount, card ID and customer ID
**matches `case_pack.csv` exactly** (HHG-014's amount is shown as "—" in the plan; actual
`$74.96`). Precedent claims were checked against `closed_cases_history.csv`; two are wrong.

| # | Case | Plan's strategic read | What the history shows | Verdict |
|---|---|---|---|---|
| D-16 | **HHG-003** | "Prior cleared false alarm — recurring subscription? (R7 innocence test)" | C08623-K2 has 6 priors: 1 cleared (**CC-1589, confirmed travel**, $99.91 @0.94) and **5 confirmed fraud** (CC-2817, CC-2935, CC-3682, CC-4957 out-of-region; CC-3327 account takeover, $528.69). Nothing suggests a subscription; the flagged txn is in-person (`W`), region 330 | Re-frame as: chronic out-of-region / ATO victim disputing an in-person $49 charge in region 330. Check region-330 history first, then R2 |
| D-17 | **HHG-007** | "19 priors, frequent travel — billing vs home region" | 19 priors: **18 confirmed fraud** (10 out-of-region, 8 account takeover) and 1 cleared (CC-0657, unusual amount confirmed — not travel). 4 priors filed SARs (CC-0765, CC-1228, CC-1524, CC-3821) | Not a "frequent traveller". This is one of the most-victimised cards in the history. Flagged txn is in-person, region 264, risk 0.87 — check whether 264 is a home or fraud region |
| D-18 | **HHG-017** | README §Answer Format "### Example" works HHG-017 as card testing (synthetic card C00377-K1, txns T0412877…, $259 purchase, customer denial, SAR filed) | Illustrative format mockup, not ground truth. Actual `case_pack.csv` row 18 is card C04570-K1, flagged txn 3450629 ($100.09, online, risk 0.57). Live `velocity_check` over the 78h burst window ending at alert time finds 3 transactions ($100.09, $99.96, $100.09) and 0 sub-$5 micro-authorizations. The in-query burst test implements Policy R5 verbatim ("three or more small online authorizations on one card within an hour"), so non-detection is an immutable graph data fact, not a threshold error. Card carries cleared travel prior CC-1383; legitimate verdict stands on actual evidence | Legitimate verdict (0.0898) confirmed on actual graph facts |

Rows verified correct (precedent counts and characterisations):

| Case | Plan read | Verified detail |
|---|---|---|
| HHG-001 | out-of-region history, region 444 | 4 priors, all confirmed fraud (3 `out_of_region_use`, 1 `card_not_present_new_device`); **no cleared/travel prior**, so "travel-exoneration candidate" is a hypothesis with no history behind it |
| HHG-002 | CNP; device profile decisive | 1 prior (CC-4160, CNP $90.54). **Caveat:** flagged txn 3478782 is online but has **no identity record**, so the device profile cannot be decisive for the flagged txn itself; use neighbouring txns |
| HHG-004 | prior cleared case exists | CC-0696 cleared (travel) + 3 confirmed CNP (CC-1736, CC-2121, CC-3778). Flagged txn device `New`, firefox 47.0 |
| HHG-005 | ★ chronic ATO victim | 3 priors, all `account_takeover` (CC-2400, CC-2717, CC-2857; $351–$896). Flagged txn `New` iOS device |
| HHG-006 | ★ no priors; high value | 0 priors. $482.12 online, `New` device, txn risk_score only 0.25 |
| HHG-008 | 19 priors, chronic new-device | 19 priors: 11 `card_not_present_new_device`, 7 `card_not_present_fraud`, 1 cleared (CC-4819, new phone added to profile). Flagged txn device **`Found`** |
| HHG-009 | ★ no priors; micro-auth testing? | 0 priors. $30.02, `ProductCD=S`, `Found` device, risk 0.28. Card-testing hypothesis unverified until the card window is pulled |
| HHG-010 | prior cleared; high amount | CC-0873 cleared (travel). $1,000.03 online, `New` Windows/edge device, risk 0.90 |
| HHG-011 | 11 priors; card-testing victim | 11 priors: 4 `card_testing` (CC-0290, CC-2247 $4,886, CC-2673, CC-4501), 6 `card_not_present_new_device`, 1 cleared (new phone). 5 SARs filed. Flagged txn `New` SM-G610F |
| HHG-012 | ★★ prior cleared on confirmed travel | **CC-0003 verified**: cleared, "$442.92 transaction at 0.91. Cardholder confirmed travel to the billing region in question." Also CC-2370 confirmed CNP ($149.99). Flagged: in-person $30.91, region 494 |
| HHG-013 | two confirmed ATO priors | CC-1475 (ATO $1,307.98, SAR) and CC-4294 (ATO $506.01) ✓ — plus CC-3216 CNP-new-device and CC-3761 cleared ($3,891 confirmed). 4 priors total |
| HHG-014 | ★★ undocumented proxy-ring test | **Verified via identity.csv**: flagged txn 3478561 is `New`, **`IP_PROXY:ANONYMOUS`**, **`SM-G935F Build/NRD90M` / Android 7.0 / chrome 62.0 for android / 1920x1080** — the exact device profile of undocumented ring cases CC-2649, CC-2971, CC-2985, CC-3035. C13487 has no closed cases and is **not** in those cases' 23 `connected_card_ids`, so this is a new ring member. Risk score is only 0.05 |
| HHG-015 | CNP new device; one cleared | CC-1313 cleared (travel) + CC-0615, CC-3886 `card_not_present_new_device` ✓. Flagged `New` Windows 8.1 / IE 11, $599.94 |
| HHG-016 | no priors | 0 priors ✓ |
| HHG-017 | cleared false-alarm prior | CC-1383 cleared (travel) ✓. Flagged txn device `Found` but **`IP_PROXY:HIDDEN`** — not noted in the plan |
| HHG-018 | 20 priors (ATO + OOR) | 20 priors: 11 ATO, 7 OOR, 1 CNP, 1 cleared (CC-0405 travel); 9 SARs. "Multi-card customer" not verifiable until `card_id` derivation (D-15) |
| HHG-019 | OOR priors + one cleared | CC-2011 (OOR $3,059.89, SAR), CC-5026 (OOR), CC-2860 (CNP), CC-2087 cleared (travel) ✓ |
| HHG-020 | two ATO priors | CC-2277, CC-2447 ✓ (both small, $81.93 / $33.95) |

## D. Plan facts verified correct

- §1.3 D2: ~590,000 transactions (590,742), ~13,500 customers (13,553) ✓
- §1.3 D4: closed cases cover the first four months — opened 2016-07-02 → 2016-11-02, closed
  through 2016-11-06 ✓ (a small tail spills into early November)
- §3 G1: 5,565 closed cases ✓
- §4 T2: files are `cases/<case_id>.json` ✓
- §4 T3: SAR zero-out (`narrative ""`, `subjects []`, total 0, dates `[]`) ✓ verbatim in README
- §4 T4 / §6.8: `BLOCK_CARD` > $2,500 → L2; `FILE_REPORT` → L2 always ✓ (plan omits that
  `DECLINE_TRANSACTION` is L1 and `BLOCK_ALL_CARDS` is L2 — both now in `bank_policy.md`)
- §6.8: R1–R10 exist and are numbered as the plan assumes ✓
- Five known patterns exist with the names the plan uses ✓
