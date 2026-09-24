"""Expected-loss calculus and Value of Information (VOI) gate for graph queries.

The gate IS the delay-cost threshold; this renders the loop's real decision in USD, it does not invent a delay model.
"""

from __future__ import annotations

from typing import Any

from agent import scoring as S
from agent.loop import MARGINAL_GATE, QUERY_FEATURES, expected_gain


def economics(probability: float, exposure_usd: float, features: Any, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Expected-loss calculus rendering the marginal-value stopping gate in USD.

    The gate IS the delay-cost threshold; this renders the loop's real decision in USD, it does not invent a delay model.
    """
    w = weights if weights is not None else S.DEFAULT_WEIGHTS
    seen = getattr(features, "queries_seen", set())
    gains = {q: expected_gain(q, features, probability, w) for q in QUERY_FEATURES if q not in seen}
    if not gains:
        q_star = None
        gain = 0.0
        p_shift = 0.0
        voi_usd = 0.0
        gate_usd = MARGINAL_GATE * probability * (1.0 - probability) * exposure_usd
        go = False
        reading = "All evidence gathered \u2014 decision made on complete information."
    else:
        q_star = max(gains, key=gains.get)
        gain = gains[q_star]
        p_shift = gain * probability * (1.0 - probability)
        voi_usd = p_shift * exposure_usd
        gate_usd = MARGINAL_GATE * probability * (1.0 - probability) * exposure_usd
        go = gain >= MARGINAL_GATE
        reading = f"Next best query {q_star}: expected information value \u2248 ${voi_usd:,.2f} vs cost-of-delay gate \u2248 ${gate_usd:,.2f} \u2192 {'gather more evidence' if go else 'stop and act'}."

    return {
        "probability": float(probability),
        "exposure_usd": float(exposure_usd),
        "at_risk_usd": round(probability * exposure_usd, 2),
        "next_query": q_star,
        "expected_logit_gain": gain,
        "expected_probability_shift": round(p_shift, 4),
        "value_of_information_usd": round(voi_usd, 2),
        "cost_of_delay_gate_usd": round(gate_usd, 2),
        "continue_gathering": go,
        "reading": reading,
    }
