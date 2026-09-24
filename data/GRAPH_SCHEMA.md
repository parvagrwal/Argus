# Graph Schema — P1 (verified against the real CSV headers)

Built 2026-09-24 for graph `FraudInvestigation` (env `TG_GRAPHNAME`) on the SENTINEL Savanna
workspace. Every vertex, edge, attribute and query below is traced to a column that exists in
`data/INVENTORY.md`. Proposals that no column supports were dropped and are listed in §5.
The P0 audit files (`INVENTORY.md`, `ANSWER_FORMAT.md`, `DISCREPANCIES.md`, `regulatory/*`) were
read, not edited.

Files: `graph/schema.gsql` (ADD-only schema-change job), `graph/queries/*.gsql` (seven queries),
`graph/card_id.py` (card derivation), `graph/setup_graph.py` (install + batch load + verify),
`mcp/fallback_rest.py` (allow-listed REST++ access, offline mock), `mcp/trace.py` (call trace).

## 1. Headers actually read

| File | Columns used | Not used |
|---|---|---|
| `transactions.csv` (397 cols) | `TransactionID, TransactionDT, TransactionAmt, ProductCD, card6, addr1, addr2, P_emaildomain, R_emaildomain, customer_id, ts, channel, risk_score` | `card1–card5` (see §3), `dist1/2`, `C1–C14`, `D1–D15`, `M1–M9`, `V1–V339` — unnamed model features (AGENTS.md §9). Never loaded whole; chunk-read with explicit `usecols`. |
| `identity.csv` (41 cols) | `TransactionID, id_15, id_23, id_30, id_31, id_33, id_34, DeviceType, DeviceInfo` | `id_01–id_14, id_16–id_22, id_24–id_29, id_32, id_35–id_38` (unnamed) |
| `closed_cases_history.csv` (15 cols) | all 15 | — |
| `case_pack.csv` (8 cols) | `case_id, flagged_txn_id, card_id, customer_id, opened_at` (validation and smoke tests only; never loaded into the graph) | — |

## 2. Vertices and edges (all supported by real columns)

| Vertex | Primary id | Attributes ← columns | Count (dry-run) |
|---|---|---|---|
| `Customer` | `customer_id` | none besides the id — no customer columns exist | 13,553 |
| `Card` | derived `card_id` (§3) | `customer_id`, `card6`, `k_index` | 14,317 |
| `Transaction` | `TransactionID` | `transaction_dt←TransactionDT`, `amount←TransactionAmt`, `product_cd←ProductCD`, `channel`, `ts`, `risk_score`, `addr1`, `addr2`, `card_id` (derived), `customer_id`, `p_emaildomain←P_emaildomain`, `r_emaildomain←R_emaildomain`, `device_status←id_15`, `proxy_flag←id_23`, `device_type←DeviceType`, `match_status←id_34`, `device_profile` (derived string) | 590,742 |
| `DeviceProfile` | `"DeviceInfo | id_30 | id_31 | id_33"` (README `connected_device_profiles` format) | `device_info, os, browser, screen` | 9,705 (the all-blank profile — 3,648 identity rows — is **not** a vertex) |
| `EmailDomain` | domain string | — | 60 (59 purchaser + 60 recipient domains, union) |
| `BillingRegion` | `addr1` code as string | — | 332 |
| `ClosedCase` | `case_id` | all 15 columns (`report_filed` → BOOL) | 5,565 |
| `InvestigationCase` | `graph_case_id` (Argus-generated) | `case_id, status, verdict, fraud_probability, pattern, exposure_usd, summary, written_at, payload_json` — all AnswerFile fields | 0 until P2 writes cases |

| Edge (directed, with reverse edge) | From → To | Source column | Count (dry-run) |
|---|---|---|---|
| `OWNS_CARD` / `CARD_OWNED_BY` | Customer → Card | derivation | 14,317 |
| `TRANS_ON_CARD` / `CARD_HAS_TRANS` | Transaction → Card | derivation | 590,742 |
| `HAS_DEVICE` / `DEVICE_SEEN_ON` | Transaction → DeviceProfile | identity join on `TransactionID` | 140,784 |
| `USES_EMAIL` / `EMAIL_USED_BY` | Transaction → EmailDomain | `P_emaildomain` | 496,262 |
| `RECIPIENT_EMAIL` / `EMAIL_RECEIVED_BY` | Transaction → EmailDomain | `R_emaildomain` (R6 "same recipient email") | 137,453 |
| `BILLED_IN` / `REGION_BILLS` | Transaction → BillingRegion | `addr1` (blank on 65,739 rows → no edge) | 525,003 |
| `PRIOR_CASE_ON` / `CARD_HAS_PRIOR_CASE` | ClosedCase → Card | `card_id` | 5,565 |
| `CASE_INCLUDES_TXN` / `TXN_IN_CLOSED_CASE` | ClosedCase → Transaction | `txn_ids` (pipe-split) | 14,955 |
| `CASE_CONNECTED_CARD` / `CARD_CONNECTED_TO_CASE` | ClosedCase → Card | `connected_card_ids` (4 rows × 23) | 92 |
| `INVESTIGATION_ON_CARD`, `INVESTIGATION_EVIDENCE_TXN`, `INVESTIGATION_EVIDENCE_DEVICE`, `INVESTIGATION_CITES_PRIOR` | InvestigationCase → Card / Transaction / DeviceProfile / ClosedCase | written by `write_fraud_case` from AnswerFile fields | 0 until P2 |

Design notes
- `USES_EMAIL` was split into two edge types instead of one edge with a `role` attribute:
  a transaction frequently has `P_emaildomain == R_emaildomain`, and two edges between the same
  pair would collapse into one without a DISCRIMINATOR (version-sensitive feature). The proposed
  name `USES_EMAIL` is kept for the purchaser domain.
- `InvestigationCase` is an addition to the proposed set. It is required by step 5
  (`write_fraud_case` / `get_case_with_evidence`) and by AGENTS.md §8; its attributes are
  restricted to fields that exist in `data/ANSWER_FORMAT.md`.
- Identity fields are copied onto `Transaction` (denormalised) so `card_window` can print
  `device_status` / `proxy_flag` without a second hop; `DeviceProfile` remains the hub for
  cross-card traversal.

## 3. Card-ID derivation (validated before any write)

**Problem.** `transactions.csv` has no `card_id`; case files use `Cxxxxx-Kn` (D-15).

**Measured facts.**
- `card1` is one-to-one with `customer_id` (13,553 distinct each; no `card1` spans two
  customers; no customer has two `card1` values) → `card1` identifies the customer, not a card.
- The card-ID prefix equals `customer_id` on all 5,565 closed cases and all 20 pack cases.
- Within a labelled card, `card2` varies in 25 of 1,913 cards and `card5` in 19; `card3`,
  `card4`, `card6` never vary → the key cannot include `card2` or `card5`.
- `K2` cards exist **only** for customers with ≥ 2 distinct `card6` values; `K3` only with 3.

**Rule adopted** (`graph/card_id.py`):

```
card_id = f"{customer_id}-K{k}"
k = 1-based rank of the row's card6 among the customer's distinct card6 values,
    sorted ascending with blank/missing first  ("" < "charge card" < "credit" < "debit" < "debit or credit")
```

**Grid search over candidate keys × orderings** (txn-level match against 14,955 labelled
closed-case transactions):

| Key | first-seen | last-seen | sorted asc | sorted desc | by count |
|---|---|---|---|---|---|
| `card6` | 0.340 | 0.993 | **1.000** | 0.333 | 0.341 |
| `card4+card6` | 0.340 | 0.993 | **1.000** | 0.333 | 0.341 |
| `card3+card4+card6` | 0.340 | 0.992 | 0.341 | 0.991 | 0.341 |
| `card2..card6` tuple | 0.378 | 0.930 | 0.392 | 0.944 | 0.384 |
| `card4` alone | — | 0.998 | 0.998 | — | — (4 customer×card4 keys map to 2 card IDs → invalid) |
| `card5` alone | — | 0.966 | — | — | — (19 labelled cards span 2 values → invalid) |

**Validation of the adopted rule** (`python -m graph.card_id`, also stored in
`data/derived/card_id_validation.json`):

| Check | Result |
|---|---|
| Closed-case transactions matching their labelled `card_id` | 14,955 / 14,955 (mismatch rate 0.0) |
| Closed cases fully matched | 5,565 / 5,565 |
| Case-pack flagged transactions matching `card_id` | 20 / 20 |
| `connected_card_ids` present among derived cards | 92 / 92 (24 distinct) |
| Derived cards / customers | 14,317 / 13,553 (12,793 customers ×1 card, 756 ×2, 4 ×3) |

**Collisions and ambiguities.**
- `card4+card6` also scores 100 % on every label; the two keys differ for exactly one customer,
  `C11039` (rows `visa|credit`, `visa|debit`, `<blank>|credit`). `card6` alone treats the blank
  `card4` as missing data on the same credit card (2 cards); `card4+card6` would call it a third
  card. `C11039` appears in no closed case and no pack case, so the labels cannot arbitrate. The
  minimal key (`card6`) is adopted; the alternative is one flag away (`CARD_KEY_COLUMNS`).
- 18 labelled `K1` cards have an all-blank `card2–card6` tuple; the rule handles them because
  blank sorts first.
- The rule is total: every transaction row gets a card (no unmapped rows), and it is stable
  under re-runs (pure function of the set of `(customer_id, card6)` pairs, not of row order).
- Any future mismatch (`ValidationReport.material`) aborts `setup_graph.py` before a single
  upsert.

## 4. Queries (graph/queries/) — algorithm and pattern evidenced

| Query | Algorithm | Pattern / rule | Real fields |
|---|---|---|---|
| `card_window(card, window_start, window_end, max_rows=500)` | 1-hop Card→Transaction scan with DATETIME range, heap-sorted by `ts`; plus Card→ClosedCase memory | evidence base for every pattern; R5 sequences; prior-case memory for `similar_prior_cases` | `ts, amount, product_cd, channel, addr1, addr2, risk_score, device_status, proxy_flag, device_profile, p/r_emaildomain`; ClosedCase.* |
| `velocity_check(card, window_start, window_end, small_amount=5, burst_minutes=60, min_small_auths=3, large_amount=100, followup_hours=24)` | sliding-window burst count over ts-sorted rows; micro-auth run followed by larger purchase | `card_testing` (R5), CNP bursts (pattern 2) | `ts, amount, channel, product_cd` |
| `device_neighbors(card, window_start, window_end, max_device_txns=200)` | 2-hop Card→DeviceProfile→Card expansion with hub suppression; neighbour cards annotated with confirmed-fraud priors | `card_not_present_new_device`, R6 shared device, `connected_card_ids` / `connected_device_profiles` | DeviceProfile (id_30/31/33, DeviceInfo), `device_status` (id_15), `proxy_flag` (id_23) |
| `detect_fraud_ring(card, window_start, window_end, max_hops=3, max_device_txns=200, max_component=500, include_email=false, max_email_txns=50)` | seeded connected-component (bounded BFS/WCC) over shared DeviceProfiles, optional rare recipient-domain links; hubs skipped | R6 / R9 coordinated abuse; the SM-G935F anonymous-proxy ring (CC-2649/2971/2985/3035) | as above + `R_emaildomain`, ClosedCase.outcome/pattern |
| `region_profile(card, flagged_region, window_start, window_end)` | MapAccum histograms of `addr1` baseline vs window, argmax home region, first/last seen, home-activity-continued flag | `out_of_region_use` (pattern 4), travel exoneration (716 cleared cases) | `addr1, addr2, ts, channel, amount` |
| `write_fraud_case(graph_case_id, case_id, card_id, status, verdict, fraud_probability, pattern, exposure_usd, summary, affected_txn_ids, device_profiles, prior_case_ids, payload_json)` | upsert InvestigationCase + evidence edges; targets resolved against existing vertices only; missing ids reported, never created | memory write (AGENTS.md §8, Policy 3a) | AnswerFile fields |
| `get_case_with_evidence(graph_case_id)` | point lookup + 1-hop over the four evidence edges; returns `payload_json` for byte-equality read-back | memory read-back verification | InvestigationCase.*, Card/Transaction/DeviceProfile/ClosedCase ids |

Semantics that differ from the proposal
- **`region_profile`** — the proposal said "billing vs transaction region distribution". The data
  has a single region field (`addr1`, billing region code) and a country code (`addr2`); there is
  no merchant location or transaction region. The query therefore compares the card's
  *baseline* billing-region history with the region of the flagged activity.
- **`detect_fraud_ring`** — WCC runs over shared device profiles. Shared *e-mail* is domain-only
  (`gmail.com` links most of the bank) so e-mail linking is off by default and, when on, limited
  to domains with ≤ `max_email_txns` recipient edges. Generic device profiles with more than
  `max_device_txns` transactions are reported as hubs and not traversed.
- **`device_neighbors`** — "2-hop Card–Device–Card" is four edge hops in this schema
  (Card–Transaction–Device–Transaction–Card) because devices attach to transactions, not cards.

## 5. Dropped or changed proposals (and why)

| Proposal | Decision | Reason |
|---|---|---|
| `IP` vertex / `USES_IP` edge | **dropped** (never allowed) | no IP address anywhere in the data (D-13); `id_23` is a proxy *flag*, kept as `Transaction.proxy_flag` |
| `Merchant` vertex / merchant field | **dropped** (never allowed) | no merchant identifier in any file (D-13); R7 "same merchant" cannot be evidenced from the graph |
| `SIMILAR_TO`, `FLAGGED_BY` edges, vector attribute on Transaction | dropped | no columns support them; not in the P1 proposal |
| `USES_EMAIL` with `role` attribute | changed to `USES_EMAIL` + `RECIPIENT_EMAIL` | P and R domains are often identical; two edges on one pair need a DISCRIMINATOR |
| Card key `card1..card6` tuple | rejected | `card1` = customer; `card2`/`card5` vary inside a labelled card (§3) |
| "transaction region" in `region_profile` | changed | only `addr1` (billing region) and `addr2` (country) exist |
| E-mail-based WCC by default | changed to opt-in | domain-only field; `gmail.com` is a hub |
| Card→Device direct edge (`HAS_DEVICE` from Card) | changed: `HAS_DEVICE` is Transaction→DeviceProfile | identity rows are per transaction; a direct Card→Device edge would lose `ts`, `id_15` and `id_23` context. Card–Device reachability is one extra hop |
| `Customer` attributes | none | no customer columns exist |
| Unnamed features (`V*`, `C*`, `D*`, `M*`, most `id_*`) | not loaded | AGENTS.md §9: usable only as declared unnamed signals; nothing in P1 needs them |
| `case_pack.csv` in the graph | not loaded | exam inputs; loading them would let retrieval "find" the answer key |

## 6. Access layer guarantees (`mcp/`)

- Allow-list = `get_schema` + the seven query names above, derived from the files in
  `graph/queries/` at import time, so it cannot drift. Unknown query names, unknown or missing
  parameters, and wrongly typed parameters (`DATETIME` must be `YYYY-MM-DD HH:MM:SS`, `INT`
  rejects bools, `SET<STRING>` needs strings) are refused before any network call.
- `GraphClient` (investigation side) has no method that accepts GSQL text or performs deletes.
  `GraphAdmin` (setup only) refuses any GSQL containing `DROP`, `DELETE`, `CLEAR`, `TRUNCATE`,
  `GRANT`, `REVOKE`, secret/user management, and any statement outside the install allow-list
  (`CREATE GRAPH`, `USE GRAPH`, schema-change jobs, `CREATE OR REPLACE QUERY`, `INSTALL QUERY`,
  loading jobs). Upserts are accepted only for schema-declared types.
- Auth: the secret-derived bearer token is used for REST++ *and* GSQL (it carries the roles of
  the account that created the secret and is scoped to `TG_GRAPHNAME`, so every GSQL batch
  begins with `USE GRAPH`); basic auth is the fallback. Note: the DB user in `TG_USERNAME` has no
  graph role on SENTINEL, so basic-auth GSQL is refused by the cluster; the token path is the one
  that works.
- Offline: missing/placeholder credentials, an unreachable or "starting" workspace, or
  `ARGUS_FORCE_MOCK=1` yield `MockGraphClient`: same allow-list, same traces, empty results
  stamped `"_mock": true`. Mock output is never evidence.
- Logs and traces redact host workspace ids and any key containing `secret`, `password`,
  `token`, `api_key` or `authorization`; `TGConfig.__repr__` never shows credentials.
- Every call becomes a `ToolCall` in `InternalCaseRecord.tool_trace`; the official file receives
  only `tool_calls` (int) and `latency_s` from `TraceRecorder.official_counts()` (D-08).

## 7. Loading (`python -m graph.setup_graph`)

- `--dry-run`: derive → validate → count, no network. Output above; 17.8 s on the full file,
  297 upsert requests of ≤ 2,000 transactions, peak memory ≈ one 50k-row × 13-column chunk plus
  the 144k-row identity lookup and the 590k-entry `TransactionID→card_id` map.
- `--schema`: fetch live schema, emit an ADD-only schema-change job for missing types only.
  If the graph itself is missing it issues `CREATE GRAPH` (needs a global-role credential).
- `--queries`: `CREATE OR REPLACE QUERY` for each file (graph name substituted from
  `TG_GRAPHNAME`), then one `INSTALL QUERY`.
- `--load [--limit N]`: batch upserts in the order Customers/Cards → Transactions (+ dimension
  vertices/edges per chunk) → ClosedCases; edges only to IDs that exist.
- `--verify`: read-only counts by type, list installed queries, one smoke run of every
  read-only query on the first pack card, and `get_case_with_evidence` on a non-existent id.
  Nothing is written during verification, so no test vertices pollute later retrieval.

Live status on SENTINEL is recorded in §8 (updated at the end of the P1 session).

## 8. Live run log (SENTINEL, 2026-09-24)

Workspace pinged ready (it had been auto-suspended; `/api/ping` returns 202 "starting" while it
wakes). Graph `FraudInvestigation` existed with no types.

| Step | Result |
|---|---|
| `--schema` | 21 types added (8 vertex, 13 edge) via one ADD-only schema-change job; nothing dropped |
| `--queries` | 7 × `CREATE OR REPLACE QUERY` + one `INSTALL QUERY`; all seven listed by `/restpp/endpoints` |
| `--load` (full) | 590,742 transactions, 144,432 identity rows, 5,565 closed cases in 273.5 s, 307 upsert requests; server accepted 1,171,022 vertices and 1,925,173 edges, **0 skipped** |
| `--verify` vertex counts (exact) | Customer 13,553 · Card 14,317 · Transaction 590,742 · DeviceProfile 9,705 · EmailDomain 60 · BillingRegion 332 · ClosedCase 5,565 · InvestigationCase 0 — identical to the dry-run |
| `--verify` edge counts | all nine edge types equal the dry-run figures and their reverse edges (the `stat_edge_number` builtin lagged by ~0.2 % for about a minute after the load, then converged) |
| smoke queries | `card_window`, `velocity_check`, `device_neighbors`, `detect_fraud_ring`, `region_profile`, `get_case_with_evidence` all return 200 with the expected result blocks; nothing was written |

Two live findings fixed during the session: typed `VERTEX<Card>` parameters must be posted as
`{"id": ..., "type": "Card"}` (now `restpp_params`), and GSQL must be authenticated with the
secret-derived token because the `TG_USERNAME` DB user has no graph role.
