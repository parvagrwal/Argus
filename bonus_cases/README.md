# Autonomous Exam-Period Monitor Cases

These cases were found by the autonomous exam-period monitor (README D9). They count toward Innovation, not accuracy.

- **Run Date**: 2026-09-24 18:41:34 UTC
- **Flag Rule**: `ts >= 2016-11-01` (exam period) AND `risk_score > 0.80`, excluding benchmark cards. Grouped by card, ordered by max `risk_score` descending (top 5 distinct cards).

## Investigated Bonus Cases
| Bonus ID | Card ID | Fraud Probability | Verdict | Pattern |
| :--- | :--- | :--- | :--- | :--- |
| `BONUS_001` | `C00750-K2` | 0.8504 | `fraud` | `none` |
| `BONUS_002` | `C06962-K2` | 0.9778 | `fraud` | `account_takeover` |
| `BONUS_003` | `C06464-K1` | 0.9840 | `fraud` | `card_not_present_new_device` |
| `BONUS_004` | `C01154-K1` | 0.8852 | `fraud` | `account_takeover` |
| `BONUS_005` | `C02716-K2` | 0.8613 | `fraud` | `none` |
