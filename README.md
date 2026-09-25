# Argus — Agentic Fraud Investigation on TigerGraph

Argus is an agentic fraud-investigation system built for the TigerGraph Agentic Fraud Investigation hackathon (Hacker House Goa, 2026). Given a trigger — a risky transaction — the agent investigates on a TigerGraph graph: traversing card/device/identity relationships, gathering evidence through a controlled query budget, scoring risk deterministically, and recommending next-best-actions with exact approval routes under the bank's fraud policy.

**Results:** 20/20 benchmark cases pass the policy-grounded grader · 16 fraud / 4 legitimate · 99 tests green · any investigation replayable offline in ~2 seconds with zero credentials.

## Live demo

- **Investigation browser:** <Vercel URL — https://argus-ruby.vercel.app/>
- **Demo video (3 min):** <link — https://youtu.be/fjdlNvSULTo>
- **Blog** <link - https://medium.com/@parvagarwal143/argus-teaching-an-ai-agent-to-investigate-fraud-like-an-analyst-and-know-when-to-stop-5dc57832d234>
- **Social Post** - <link - https://x.com/ParvAga51412455/status/2103265714295672878>

## 60-second quickstart (no credentials needed)

```bash
pip install -r requirements.txt
python demo.py --offline            # full investigation of HHG-014 on recorded fixtures (~2 s)
python demo.py --ablate-memory      # memory ablation on HHG-012: verdict flips, |Δp| = 0.9384
python -m pytest -q
```

Tests: 99 passed, 2 skipped (the 2 skips need the raw dataset CSVs, which are not committed).

`--offline` runs the real pipeline (`agent/loop.py`, `agent/scoring.py`, `agent/policy.py`) against 125 fixtures recorded from live TigerGraph runs. It asserts no TigerGraph credentials are set, so what you see is deterministic replay — no mocks.

## How it works

1. **Trigger.** A case opens from a risk-scored transaction (`data/case_pack.csv`, 20 benchmark cases).
2. **Playbook loop** (`agent/loop.py`). Five data-chosen investigation archetypes; each step picks the highest-value unasked query. Hard stops at fraud probability 0.85 / 0.15, a 12-query cap, and a marginal-value gate that stops asking when the next query can't move the decision.
3. **Deterministic scoring** (`agent/scoring.py`). 23 graph-derived features through a logistic model with policy-grounded prior weights. No LLM in the scoring path — the LLM narrates, never computes.
4. **Policy engine** (`agent/policy.py`). Bank Fraud Policy §1–§7 as decision tables: action allow-list, approval routes, SAR triggers, and the §6 rule requiring two independent evidence items before a fraud verdict.
5. **Next-best-actions + write-back.** Every case file records NBA before and after evidence (`what_changed`); confirmed fraud is written back to the graph as an `InvestigationCase` vertex with a read-back check.

## Results

| | |
|---|---|
| Benchmark | 20/20 PASS, 0 warnings (`scripts/grade.py`) |
| Verdicts | 16 fraud (0.87–0.999) · 4 legitimate (0.045–0.13) |
| SARs filed | 6, per Policy §3a |
| Tests | 99 passed, 2 skipped |

**Showcase cases:**

- **HHG-014** — 19-card shared-proxy device ring, fraud at 0.996, SAR filed. Found via `detect_fraud_ring` + `device_neighbors`.
- **HHG-012** — the memory-ablation star: with case memory, legitimate at 0.0454 (a cleared travel prior exonerates); without it, fraud at 0.9838. |Δp| = 0.9384.
- **HHG-017** — graph evidence alone leaves 0.66 (uncertain) → agent requests customer confirmation → confirmed legitimate → 0.0898. The policy loop working as designed.
- **BONUS_001–005** — five extra fraud cases found by the agent's own autonomous exam-period monitor (D9), all fraud at 0.85–0.98.

## Innovation highlights

- **Case-memory ablation** (`demo.py --ablate-memory`, `ablation_report.json`) — measures exactly how much prior-case memory moves each verdict.
- **Economics of investigation** (`agent/ev.py`) — every query's expected information value in USD vs. a cost-of-delay gate. The agent stops asking and acts when the math says so.
- **Deterministic counterfactuals** (`agent/counterfactual.py`) — "no single evidence change flips this decision" — or the one that does, in one sentence.
- **Autonomous D9 monitor** (`scripts/autonomous_monitor.py`, `bonus_cases/`) — the agent kept investigating on its own during the exam period and found 5 real fraud cases.
- **Rejected calibration** (`scripts/calibration/`) — we fit weights on 5,565 closed cases and threw the fit away: analyst-notes features leaked the label (in-sample AUC 1.0000) and inverted genuine signals. Policy-grounded priors kept. The negative result is committed, not hidden.
- **Hybrid graph+vector recall** (`agent/vector_memory.py`) — closed-case analyst notes embedded (all-MiniLM-L6-v2, 384-dim) and stored as TigerGraph VECTOR attributes; the agent retrieves the most similar prior cases by cosine similarity as investigative context. Vector recall never touches scoring and never counts toward the §6 evidence minimum.

## Repository map

| Path | What it is |
|---|---|
| `agent/` | The agent: scoring, policy engine, investigation loop, economics, counterfactuals, answer writer |
| `cases/` | 20 benchmark answer files: verdict, probability, pattern, evidence, NBA initial/final/`what_changed`, SAR, tool-call traces |
| `bonus_cases/` | 5 autonomous D9 discoveries (innovation, not accuracy) |
| `graph/` | GSQL schema, 7 installed queries, loading jobs (590,742 transactions · 1.9M edges on Savanna `SENTINEL`) |
| `mcp/` | TigerGraph MCP wiring |
| `fixtures/` | 125 fixtures recorded from live runs + `FixtureClient` (powers `--offline`) |
| `scripts/` | `run_all_cases.py`, `grade.py`, `record_fixtures.py`, `export_web_bundle.py`, `calibration/` |
| `web/` | Static Next.js investigation browser (Vercel): 25 cases × 6 panels, network viz, ablation strip |
| `demo.py` | CLI: live/offline investigations, memory ablation, ablation sweep |
| `ablation_report.json` | Ablation results over all 20 cases |
| `data/` | Dataset README + case pack (raw CSVs not committed) |

## Policy ground truth (enforced in code)

- Hard stops at **0.85 / 0.15** fraud probability.
- Fraud verdicts require **two independent evidence items** (Policy §6) — not three, not "two source types."
- **0.70 is R1 "verify-before-block"**, not a SAR threshold. SAR filing follows **§3a** triggers.
- The LLM narrates; it never computes a score.

## Honesty notes

- The Vercel UI **replays recorded investigations** — labeled as such on the site. The investigations ran live on TigerGraph; `demo.py --offline` replays them deterministically.
- `demo.py --ablate-sweep` refuses to run without live credentials or `--offline`: it will not overwrite the committed ablation report with mock data.

## Running live

With TigerGraph Savanna credentials set (`TG_HOST`, `TG_SECRET`), `python demo.py --case-id HHG-014` investigates live against the `FraudInvestigation` graph. Without credentials, everything above runs offline on fixtures.
