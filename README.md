# Argus — Agentic Fraud Investigation on TigerGraph

Argus is an agentic fraud-investigation system built for the TigerGraph Agentic Fraud Investigation hackathon (Hacker House Goa, 2026). Given a trigger (a risky transaction), the agent investigates on a TigerGraph graph — traversing card/device/identity relationships, gathering evidence through controlled queries, scoring risk deterministically, and recommending next-best-actions with exact approval routes under the bank's fraud policy.

## 60-second quickstart (no credentials needed)

```bash
pip install -r requirements.txt
python demo.py --offline            # full investigation of HHG-014 on recorded fixtures (~2 s)
python demo.py --ablate-memory      # case-memory ablation on HHG-012: 0.0454 → 0.9838, verdict flips
python -m pytest -q
```

Tests: 99 passed, 2 skipped (the 2 skips need the raw dataset CSVs, which are not committed).
```
