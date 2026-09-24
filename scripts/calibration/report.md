# Model Calibration Report — Fitted Weights on Closed Cases History

**Dataset**: `data/closed_cases_history.csv` (5565 cases fitted)
**Methodology**: L2-regularised logistic regression (`iters=2000, l2=0.05, lr=0.05`), rank-based ROC-AUC (in-sample).

> [!NOTE]
> **Caveat (Architect judgment baked in)**: Feature extraction replicates the live pipeline semantics exactly, including counting all prior closed cases on each card rather than strictly time-bounding historical case references. This guarantees that fitted weights align mathematically with the inference pipeline.

## 1. Executive Summary

- **In-Sample ROC-AUC**: Prior `0.8474` → Fitted `1.0000` (Delta: `+0.1526`)
- **Prior Bias**: `-1.6` | **Fitted Bias**: `0.2375`
- **Benchmark Cases Re-Score**: 14 verdict band flips observed at 0.85/0.15 thresholds.
- **Total Rows Skipped**: 0

## 2. Coefficient Comparison (Sorted by |Delta|)

| Feature | Prior Weight | Fitted Weight | Delta (Fitted - Prior) | |Delta| |
| :--- | :--- | :--- | :--- | :--- |
| `new_device` | 1.1000 | -0.7513 | -1.8513 | 1.8513 |
| `structuring` | 1.8000 | 0.0001 | -1.7999 | 1.7999 |
| `risk_score` | 1.2000 | -0.5579 | -1.7579 | 1.7579 |
| `ring` | 1.8000 | 0.0464 | -1.7536 | 1.7536 |
| `region_history` | -1.6000 | 0.0922 | +1.6922 | 1.6922 |
| `testing_then_purchase` | 1.6000 | 0.0000 | -1.6000 | 1.6000 |
| `micro_auth_burst` | 1.4000 | 0.0014 | -1.3986 | 1.3986 |
| `trip_pattern` | -1.2000 | 0.1198 | +1.3198 | 1.3198 |
| `customer_report` | 0.9000 | 2.1753 | +1.2753 | 1.2753 |
| `out_of_region` | 1.3000 | 0.0494 | -1.2506 | 1.2506 |
| `neighbor_prior_fraud` | 1.3000 | 0.0555 | -1.2445 | 1.2445 |
| `customer_confirmed` | -3.0000 | -1.9380 | +1.0620 | 1.0620 |
| `proxy` | 1.0000 | -0.0205 | -1.0205 | 1.0205 |
| `shared_device_cards_log` | 0.8000 | -0.0830 | -0.8830 | 0.8830 |
| `prior_cleared` | -0.4000 | -1.1308 | -0.7308 | 0.7308 |
| `online_burst_48h` | 0.8000 | 0.1025 | -0.6975 | 0.6975 |
| `mixed_channel` | 0.7000 | 0.0063 | -0.6937 | 0.6937 |
| `amount_ratio_log` | 0.5000 | -0.1484 | -0.6484 | 0.6484 |
| `cold_start` | -0.3000 | 0.0633 | +0.3633 | 0.3633 |
| `online` | 0.2000 | -0.0431 | -0.2431 | 0.2431 |
| `prior_fraud_log` | 0.9000 | 1.0461 | +0.1461 | 0.1461 |
| `customer_denied` | 2.2000 | 2.1753 | -0.0247 | 0.0247 |

## 3. Calibration Reliability Table (10 Bins)

### Prior Weights Reliability
| Bin Range | Samples (n) | Mean Predicted Prob | Observed Fraud Rate |
| :--- | :--- | :--- | :--- |
| [0.0, 0.1) | 146 | 0.0435 | 0.0000 |
| [0.1, 0.2) | 56 | 0.1378 | 0.0000 |
| [0.2, 0.3) | 21 | 0.2491 | 0.1905 |
| [0.3, 0.4) | 20 | 0.3532 | 0.6500 |
| [0.4, 0.5) | 33 | 0.4430 | 0.7879 |
| [0.5, 0.6) | 64 | 0.5520 | 0.9375 |
| [0.6, 0.7) | 95 | 0.6536 | 0.8526 |
| [0.7, 0.8) | 122 | 0.7527 | 0.8852 |
| [0.8, 0.9) | 172 | 0.8603 | 0.7674 |
| [0.9, 1.0) | 4836 | 0.9919 | 0.8770 |

### Fitted Weights Reliability
| Bin Range | Samples (n) | Mean Predicted Prob | Observed Fraud Rate |
| :--- | :--- | :--- | :--- |
| [0.0, 0.1) | 824 | 0.0234 | 0.0000 |
| [0.1, 0.2) | 51 | 0.1358 | 0.0000 |
| [0.2, 0.3) | 15 | 0.2486 | 0.0000 |
| [0.3, 0.4) | 9 | 0.3438 | 0.0000 |
| [0.4, 0.5) | 1 | 0.4498 | 0.0000 |
| [0.9, 1.0) | 4665 | 0.9927 | 1.0000 |

## 4. Benchmark 20 Cases Re-Score (Compute-Only Evaluation)

| Case ID | Prior Prob | Fitted Prob | Prior Band | Fitted Band | Flip? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `HHG-001` | 0.0981 | 0.8572 | legitimate (<=0.15) | fraud (>=0.85) | **FLIP** |
| `HHG-002` | 0.9981 | 0.5266 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-003` | 0.9232 | 0.9586 | fraud (>=0.85) | fraud (>=0.85) | No |
| `HHG-004` | 0.9999 | 0.8039 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-005` | 0.9972 | 0.6606 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-006` | 0.9938 | 0.7903 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-007` | 0.9977 | 0.8385 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-008` | 1.0000 | 0.9796 | fraud (>=0.85) | fraud (>=0.85) | No |
| `HHG-009` | 0.9965 | 0.8892 | fraud (>=0.85) | fraud (>=0.85) | No |
| `HHG-010` | 0.9990 | 0.0665 | fraud (>=0.85) | legitimate (<=0.15) | **FLIP** |
| `HHG-011` | 0.9998 | 0.9686 | fraud (>=0.85) | fraud (>=0.85) | No |
| `HHG-012` | 0.9654 | 0.3950 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-013` | 0.8708 | 0.3588 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-014` | 0.9993 | 0.2984 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-015` | 0.9998 | 0.2228 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-016` | 0.9677 | 0.8023 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-017` | 0.6646 | 0.2364 | uncertain (0.15-0.85) | uncertain (0.15-0.85) | No |
| `HHG-018` | 0.9998 | 0.9838 | fraud (>=0.85) | fraud (>=0.85) | No |
| `HHG-019` | 0.9990 | 0.3315 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |
| `HHG-020` | 0.8896 | 0.5712 | fraud (>=0.85) | uncertain (0.15-0.85) | **FLIP** |

## 5. Keyword Rules Hit Counts & Skips

- **`customer_denied` keyword matches**: 4665
- **`customer_confirmed` keyword matches**: 900
- **`customer_report` keyword matches**: 4665
- **Total Skips**: 0