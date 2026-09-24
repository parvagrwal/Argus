# The Five Known Fraud Patterns (verbatim transcription)

Source: `data/README.md`, section "The five known fraud patterns", plus every README statement
about undocumented patterns. Transcribed 2026-09-24 without paraphrase. Quoted blocks are the
README text as written; only headings and the closing "Data-side notes" were added.

---

## The five known fraud patterns

These are the patterns the bank's analysts recognize. **They are not the only patterns in the data.** Noticing activity that fits none of them, describing it in your own words, and recommending a defensible action is scored.

**1. Card testing.** A stolen card number is checked before use: three or more tiny online authorizations, often under $5, then a larger purchase. Confirmed by the sequence itself. Policy R5.

**2. Card-not-present fraud.** The number is used online without the card. Amounts and products that don't fit the cardholder's history, often in a burst of two to four within 48 hours. On its own, one unusual online purchase is ambiguous: verify. Policy R1 to R4.

**3. Card-not-present fraud from a new device.** Same as above, with the identity record marking the device as `New` for this account, sometimes behind a proxy. Stronger than pattern 2, still not proof: people buy new phones.

**4. Out-of-region use.** Card-present purchases in a billing region the cardholder has no history in, while their normal activity continues at home. Several days of purchases in one new region is a trip, not a clone. Policy R2, R3.

**5. Account takeover.** Mixed-channel activity inconsistent with the cardholder, often with device and match-flag anomalies, pointing to stolen credentials rather than a stolen number.

---

## Answer-file `pattern` values (verbatim)

`card_testing` · `card_not_present_fraud` · `card_not_present_new_device` · `out_of_region_use` · `account_takeover` · `undocumented` · `none`

The first five are described in the Known Fraud Patterns section above. Use `undocumented` when the evidence shows abuse that fits none of them, and say what you found in `pattern_description`. Finding an undocumented pattern is scored.

---

## Every README statement about undocumented patterns (verbatim)

Glossary, "Pattern":

> The kind of fraud. Five are documented below. Some in the data are not

"The five known fraud patterns" preamble:

> These are the patterns the bank's analysts recognize. **They are not the only patterns in the data.** Noticing activity that fits none of them, describing it in your own words, and recommending a defensible action is scored.

"Things to know":

> - **The known patterns are not the only ones.** Some activity in this data fits none of the five. Noticing it and describing it in your own words is scored.

`closed_cases_history.csv` section:

> Patterns are the five below, plus `undocumented` for a few cases the analysts confirmed as fraud but could not match to a known pattern. Read those notes carefully. Cleared cases have `pattern` = `none` and say why the alert was a false alarm.

Answer Format, `pattern` field:

> The fraud pattern you identified, `undocumented` if it matches none of the known ones, or `none`

Answer Format, `pattern_description` field:

> Required when `pattern` is `undocumented`: two or three sentences on what the pattern is, who it affects, and how you found it. Otherwise `""`

Fraud Policy, R9:

> **R9. Undocumented patterns.** When activity fits none of the known patterns but the evidence shows coordinated or repeated abuse across customers, recommend `CREATE_CASE`, `FILE_REPORT`, and `ESCALATE_TO_ANALYST`, and describe the pattern in your own words. Do not force it into a known category.

Fraud Policy, 3a (SAR condition):

> the pattern is coordinated or undocumented (rule R9)

---

## Related verbatim passages

"Things to know":

> - **Devices and regions connect people.** A device profile or a billing region shared across many cards in a short window is worth a look. Some cases can only be solved by asking what happened on *other* cards.

Glossary, "Channel":

> `in_person` (product code W, no device record) or `online` (all other product codes, device record present)

Glossary, "Identity record":

> The device and connection details Vesta captured for online transactions: device type and model, OS, browser, screen, proxy flag, and encoded ratings

---

## Data-side notes (not README text; from the P0 audit of `closed_cases_history.csv`)

The 9 closed cases labelled `undocumented` describe two typologies the analysts saw but did not
name. Their notes, verbatim from the CSV:

- **Anonymous-proxy device ring** (`CC-2649`, `CC-2971`, `CC-2985`, `CC-3035`): "The purchases
  came from a Samsung SM-G935F on Chrome for Android behind an anonymous proxy, a device never
  seen on this account. Two other cardholders reported the same device profile this month.
  Pattern not matched to a documented typology."
- **Sub-$500 structuring** (`CC-3748`, `CC-3841`, `CC-3907`, `CC-4086`, `CC-4124`): "four
  online purchases within forty minutes, each just under $500, none of which they made.
  Amounts appear chosen to stay under a $500 authorization threshold. Pattern not matched to a
  documented typology."

Per R9, the agent must describe such activity in its own words and never force it into one of
the five labels.
