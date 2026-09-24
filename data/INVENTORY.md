# Dataset Inventory — HHGOA_IEEE (TigerGraph × Hacker House Goa 2026)

Audited 2026-09-24 against the files in `./data/`. Source of truth is `data/README.md`
(the dataset README; there is no separate `dataset_README.md`). Every file was read once;
large CSVs were profiled for headers, dtypes and row counts only.

## Files present

| File | Size | Rows (excl. header) | Columns | README claim | Match |
|---|---|---|---|---|---|
| `README.md` | 38.7 KB | — | — | task, data, patterns, policy, answer format, 20 cases | ✅ |
| `case_pack.csv` | 3.5 KB | **20** | 8 | 20 exam cases | ✅ |
| `closed_cases_history.csv` | 2.7 MB | **5,565** | 15 | 5,565 finished investigations | ✅ |
| `identity.csv` | 26.7 MB | **144,432** | 41 | 144,432 identity records, 41 columns | ✅ |
| `transactions.csv` | 708 MB | **590,742** | 397 | 590,742 transactions, 393 Vesta cols + 4 added | ✅ |

There are **no separate policy/regulatory document files** in `./data/`. The Fraud Policy
(R1–R10), the five known patterns and the regulatory reference *links* are all sections of
`README.md`. Transcriptions live in `data/regulatory/`.

Headline verification against the Win Plan §1.3 dataset facts:

| Fact | Plan | Actual |
|---|---|---|
| Transactions | ~590,000 | 590,742 |
| Customers | ~13,500 | 13,553 distinct `customer_id` |
| Benchmark cases | 20 | 20 |
| Closed cases | 5,565 | 5,565 (4,665 `confirmed_fraud`, 900 `cleared`) |

## `case_pack.csv`

Columns (all string; `risk_score` float, empty for non-`risk_score` triggers):

`case_id, opened_at, trigger_type, trigger_text, flagged_txn_id, card_id, customer_id, risk_score`

- `trigger_type` counts: `risk_score` 11, `customer_report` 8, `analyst_request` 1.
- All 20 `flagged_txn_id` values exist in `transactions.csv`.
- **Observation:** `opened_at` is exactly **6 hours after** the flagged transaction's `ts`
  for every case (e.g. HHG-001 opened `2016-12-05 01:55:28`, txn `ts` `2016-12-04 19:55:28`).
  Treat `opened_at` as the alert time, not the transaction time.

## `closed_cases_history.csv`

Columns and inferred dtypes:

| Column | dtype | Notes |
|---|---|---|
| `case_id` | str | `CC-0001` … `CC-5565`, sequential |
| `customer_id` | str | 1,892 distinct customers |
| `card_id` | str | `Cxxxxx-Kn` |
| `opened_at` | datetime str | `2016-07-02 07:17:26` → `2016-11-02 02:00:37` |
| `closed_at` | datetime str | `2016-07-04 02:10:20` → `2016-11-06 23:39:58` |
| `outcome` | enum | `confirmed_fraud` 4,665 / `cleared` 900 |
| `pattern` | enum | see counts below |
| `first_fraud_txn_id` | int / empty | empty on cleared cases |
| `txn_ids` | str | pipe-separated transaction IDs |
| `n_txns` | int | |
| `exposure_usd` | float | 0.00 – 35,031.56, mean 372.40 |
| `connected_card_ids` | str | pipe-separated; **non-empty on only 4 rows** (the proxy-ring cases) |
| `actions_taken` | str | pipe-separated policy action names |
| `report_filed` | enum | `Yes` 397 / `No` 5,168 |
| `analyst_notes` | str | templated narrative |

Pattern counts: `card_not_present_fraud` 1,404 · `account_takeover` 1,205 ·
`card_not_present_new_device` 1,076 · `out_of_region_use` 955 · `none` 900 (all cleared) ·
`card_testing` 16 · `undocumented` 9.

`actions_taken` takes exactly three values: `CREATE_CASE|BLOCK_CARD` (4,268),
`VERIFY_WITH_CUSTOMER|CLOSE_NO_FRAUD` (900), `CREATE_CASE|BLOCK_CARD|FILE_REPORT` (397).

Cleared-case note templates (3 kinds): "Cardholder confirmed travel to the billing region in
question" (716 cases), "Cardholder confirmed the purchase from a new phone. Device added to
profile" (158), "Cardholder confirmed the purchase. Amount unusual for this customer but
consistent with their stated intent". No note mentions "recurring", "subscription" or "ring".

Undocumented cases (9) fall into two typologies:

1. **Anonymous-proxy device ring** — `CC-2649`, `CC-2971`, `CC-2985`, `CC-3035`: "Samsung
   SM-G935F on Chrome for Android behind an anonymous proxy, a device never seen on this
   account. Two other cardholders reported the same device profile this month." Each lists the
   same 23 `connected_card_ids`.
2. **Sub-$500 threshold structuring** — `CC-3748`, `CC-3841`, `CC-3907`, `CC-4086`, `CC-4124`:
   "four online purchases within forty minutes, each just under $500 … Amounts appear chosen
   to stay under a $500 authorization threshold." Exposure ≈ $1,870–$1,923 each.

Chronic account-takeover victims (most ATO cases): C11000, C01155, C11958, C01109 (13 each);
642 customers have ≥ 2 confirmed-fraud cases.

## `identity.csv`

Columns: `TransactionID, id_01 … id_38, DeviceType, DeviceInfo` (41). Joins to
`transactions.csv` on `TransactionID`. Online transactions only.

dtypes: `TransactionID` int; `id_01`–`id_11` float; `id_12` str; `id_13`, `id_14` float;
`id_15`, `id_16` str; `id_17`–`id_22` float; `id_23` str; `id_24`–`id_26` float;
`id_27`–`id_31` str; `id_32` float; `id_33`–`id_38` str; `DeviceType` str; `DeviceInfo` str.
Readable fields: `id_15` (New/Found/Unknown), `id_23` (`IP_PROXY:TRANSPARENT|ANONYMOUS|HIDDEN`),
`id_30` OS, `id_31` browser, `id_33` screen, `id_34` `match_status:n`.

**Coverage note:** 14 of the 20 flagged transactions have an identity record. The 5 in-person
(`ProductCD=W`) cases have none, as documented. **HHG-002's flagged txn `3478782` is `online`
(`ProductCD=C`) but has no identity row** — the README's "online ⇒ device record present"
does not hold universally.

## `transactions.csv`

397 columns: the 393 Vesta columns (`TransactionID, TransactionDT, TransactionAmt, ProductCD,
card1–card6, addr1, addr2, dist1, dist2, P_emaildomain, R_emaildomain, C1–C14, D1–D15, M1–M9,
V1–V339`) followed by the 4 added columns `customer_id, ts, channel, risk_score`.

- `ts` range: `2016-07-02 00:02:21` → `2016-12-31 23:58:54`.
- `channel`: `in_person` 439,670 / `online` 151,072.
- **There is no `card_id` column.** Card IDs of the form `C01234-K1` (used by `case_pack.csv`
  and `closed_cases_history.csv`) must be derived during load — README: "Derived from the card
  issuer field; one customer can have several cards." Working hypothesis for P1: enumerate
  distinct `card1` (or the `card1..card6` tuple) per `customer_id` in first-seen order → `K1, K2…`.
  Must be validated against the card IDs referenced in closed cases before the graph load.
- `addr2 = 87.0` is the home country; `addr1` is the billing region code.
- No merchant identifier and no IP address exist anywhere in the data. Devices are only
  describable as the profile tuple `DeviceInfo | id_30 | id_31 | id_33`.

## Flagged transactions of the 20 cases (from `transactions.csv` + `identity.csv`)

| Case | Txn | Amt | Prod | Channel | addr1 | risk | id_15 | Proxy | Device (DeviceInfo / OS / browser / screen) |
|---|---|---|---|---|---|---|---|---|---|
| HHG-001 | 3514030 | 77.07 | W | in_person | 444 | 0.61 | — | — | — |
| HHG-002 | 3478782 | 292.36 | C | online | (blank) | 0.79 | *no identity row* | — | — |
| HHG-003 | 3530164 | 49.00 | W | in_person | 330 | 0.40 | — | — | — |
| HHG-004 | 3583227 | 128.33 | C | online | (blank) | 0.34 | New | — | (blank) / — / firefox 47.0 / — |
| HHG-005 | 3523199 | 100.07 | R | online | 330 | 0.54 | New | — | iOS Device / iOS 9.3.5 / mobile safari 9.0 / 1024x768 |
| HHG-006 | 3476682 | 482.12 | C | online | 264 | 0.25 | New | — | Trident/7.0 / Windows 7 / ie 11.0 / 1920x1080 |
| HHG-007 | 3514948 | 111.92 | W | in_person | 264 | 0.87 | — | — | — |
| HHG-008 | 3558054 | 55.68 | C | online | (blank) | 0.38 | Found | — | (blank) / — / chrome 66.0 / — |
| HHG-009 | 3581141 | 30.02 | S | online | 203 | 0.28 | Found | — | (blank) / — / — / — |
| HHG-010 | 3506725 | 1000.03 | R | online | 469 | 0.90 | New | — | Windows / Windows 10 / edge 16.0 / 1366x768 |
| HHG-011 | 3583368 | 131.30 | C | online | (blank) | 0.39 | New | — | SM-G610F Build/NRD90M / — / chrome 66.0 for android / — |
| HHG-012 | 3553342 | 30.91 | W | in_person | 494 | 0.55 | — | — | — |
| HHG-013 | 3526826 | 35.66 | C | online | (blank) | 0.76 | New | — | Windows / — / chrome 66.0 / — |
| HHG-014 | 3478561 | 74.96 | C | online | 191 | 0.05 | New | **IP_PROXY:ANONYMOUS** | **SM-G935F Build/NRD90M / Android 7.0 / chrome 62.0 for android / 1920x1080** |
| HHG-015 | 3464869 | 599.94 | R | online | 327 | 0.77 | New | — | Trident/7.0 / Windows 8.1 / ie 11.0 / 1680x1050 |
| HHG-016 | 3534820 | 59.67 | C | online | (blank) | 0.37 | New | — | Windows / — / edge 16.0 / — |
| HHG-017 | 3450629 | 100.09 | R | online | 204 | 0.57 | Found | **IP_PROXY:HIDDEN** | Windows / Windows 10 / chrome 65.0 / 1920x1080 |
| HHG-018 | 3491361 | 39.08 | W | in_person | 126 | 0.48 | — | — | — |
| HHG-019 | 3503878 | 99.92 | R | online | 264 | 0.90 | New | — | Windows / other / chrome 61.0 / 1280x720 |
| HHG-020 | 3509359 | 125.08 | R | online | 264 | 0.52 | New | — | Trident/7.0 / Windows 10 / ie 11.0 / 1920x1080 |

`risk` above is the transaction's own `risk_score`; for `customer_report` cases the case pack
leaves it blank, but the transaction still carries one.
