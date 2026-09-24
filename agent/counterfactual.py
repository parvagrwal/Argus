"""Deterministic counterfactual explanation generator.

Calculates the minimal single-feature modification required to cross the decision boundary (0.85 for fraud, 0.15 for legitimate), rendering the verdict uncertain. No LLM here.
"""

from __future__ import annotations

import math
from typing import Any


def counterfactual(
    features: Any,
    weights: dict[str, float],
    bias: float,
    probability: float,
    verdict: str,
) -> dict[str, Any]:
    """Calculate the minimal single-feature counterfactual shift."""
    assert verdict in ("fraud", "legitimate"), f"Counterfactual requires 'fraud' or 'legitimate' verdict, got {verdict!r}"

    boundary = 0.85 if verdict == "fraud" else 0.15
    p_clamped = min(max(probability, 1e-6), 1.0 - 1e-6)
    logit_now = math.log(p_clamped / (1.0 - p_clamped))
    logit_boundary = math.log(boundary / (1.0 - boundary))
    need = logit_boundary - logit_now

    candidates: list[dict[str, Any]] = []

    for k, w in weights.items():
        if w == 0:
            continue
        v = float(getattr(features, k) if hasattr(features, k) else features.get(k, 0.0))

        if k == "risk_score":
            delta = need / w
            new_v = v + delta
            if 0.0 <= new_v <= 1.0:
                candidates.append({
                    "feature": k,
                    "kind": "risk_score",
                    "old_value": v,
                    "new_value": round(new_v, 4),
                    "abs_delta": abs(delta),
                    "w": w,
                    "new_p": boundary,
                })
        elif k.endswith("_log"):
            if v > 0:
                delta = need / w
                new_v = v + delta
                if new_v >= 0.0:
                    candidates.append({
                        "feature": k,
                        "kind": "log",
                        "old_value": v,
                        "new_value": round(new_v, 4),
                        "abs_delta": abs(delta),
                        "w": w,
                        "new_p": boundary,
                    })
        else:
            # Binary feature
            d = w * (1.0 - 2.0 * v)
            same_sign = (d > 0 and need > 0) or (d < 0 and need < 0)
            if same_sign and abs(d) >= abs(need):
                new_p = 1.0 / (1.0 + math.exp(-(logit_now + d)))
                candidates.append({
                    "feature": k,
                    "kind": "binary",
                    "old_value": v,
                    "new_value": int(1.0 - v),
                    "abs_delta": 1.0,
                    "w": w,
                    "new_p": new_p,
                })

    if not candidates:
        return {
            "flips": False,
            "sentence": "No single evidence change flips this decision — the verdict is robust to any one feature.",
        }

    # Pick the valid candidate with smallest |delta|; tie-break on larger |w|
    best = min(candidates, key=lambda c: (c["abs_delta"], -abs(c["w"])))

    k = best["feature"]
    v = best["old_value"]
    new_v = best["new_value"]
    new_p = best["new_p"]
    kind = best["kind"]

    if kind == "binary":
        sentence = f"If {k} were {int(1 - v)} instead of {int(v)}, fraud probability would move from {probability:.2f} to {new_p:.2f}, crossing the {boundary:.2f} decision boundary — the verdict would become uncertain."
    elif kind == "risk_score":
        sentence = f"If risk_score were {new_v:.2f} instead of {v:.2f}, fraud probability would move from {probability:.2f} to {new_p:.2f}, crossing the {boundary:.2f} decision boundary — the verdict would become uncertain."
    else:  # kind == "log"
        old_n = round(math.exp(v) - 1.0)
        new_n = round(math.exp(new_v) - 1.0)
        name = k[:-4].replace("_", " ") if k.endswith("_log") else k.replace("_", " ")
        sentence = f"If {name} were {new_n} instead of {old_n}, fraud probability would move from {probability:.2f} to {new_p:.2f}, crossing the {boundary:.2f} decision boundary — the verdict would become uncertain."

    return {
        "flips": True,
        "feature": k,
        "old_value": v,
        "new_value": new_v,
        "old_probability": round(probability, 4),
        "new_probability": round(new_p, 4),
        "boundary": boundary,
        "sentence": sentence,
    }
