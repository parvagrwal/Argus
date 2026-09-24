"""Unit tests for agent/ev.py — Expected-loss calculus and VOI stopping gate."""

from __future__ import annotations

from agent.ev import economics
from agent.loop import MARGINAL_GATE
from agent.scoring import Features


def test_ev_hhg014_hand_computed_vector():
    """Verify hand-computed vector for HHG-014."""
    # Build faithful features matching HHG-014 post-device_neighbors
    f = Features(
        risk_score=0.05,
        online=1.0,
        new_device=1.0,
        proxy=1.0,
        amount_ratio_log=0.7362,
        mixed_channel=1.0,
        shared_device_cards_log=2.9957,
        neighbor_prior_fraud=1.0,
        queries_seen={"card_window", "device_neighbors"},
    )
    p = 0.9960
    exposure = 74.96

    res = economics(p, exposure, f)

    assert res["probability"] == 0.9960
    assert res["exposure_usd"] == 74.96
    assert res["at_risk_usd"] == 74.66
    assert res["cost_of_delay_gate_usd"] == 0.01
    assert res["value_of_information_usd"] == 0.00
    assert res["continue_gathering"] is False
    assert res["next_query"] == "velocity_check"

    # Assert gain is computed dynamically and equals function's own output
    gain = res["expected_logit_gain"]
    assert res["continue_gathering"] == (gain >= MARGINAL_GATE)

    expected_reading = (
        "Next best query velocity_check: expected information value \u2248 $0.00 "
        "vs cost-of-delay gate \u2248 $0.01 \u2192 stop and act."
    )
    assert res["reading"] == expected_reading


def test_ev_gate_boundary():
    """Verify continue_gathering behavior around MARGINAL_GATE threshold."""
    # High uncertainty (p=0.5) with unseen queries yields gain >= 0.04 -> continue_gathering True
    f_uncertain = Features(queries_seen={"card_window"})
    res_high = economics(0.50, 1000.0, f_uncertain)
    assert res_high["expected_logit_gain"] >= MARGINAL_GATE
    assert res_high["continue_gathering"] is True

    # Low uncertainty (p=0.9960) with small gain < 0.04 -> continue_gathering False
    f_settled = Features(
        risk_score=0.05,
        online=1.0,
        new_device=1.0,
        proxy=1.0,
        amount_ratio_log=0.7362,
        mixed_channel=1.0,
        shared_device_cards_log=2.9957,
        neighbor_prior_fraud=1.0,
        queries_seen={"card_window", "device_neighbors"},
    )
    res_low = economics(0.9960, 74.96, f_settled)
    assert res_low["expected_logit_gain"] < MARGINAL_GATE
    assert res_low["continue_gathering"] is False


def test_ev_determinism():
    """Verify that multiple calls with identical arguments return identical dictionaries."""
    f = Features(
        risk_score=0.25,
        online=1.0,
        new_device=1.0,
        queries_seen={"card_window"},
    )
    res1 = economics(0.75, 500.0, f)
    res2 = economics(0.75, 500.0, f)
    assert res1 == res2


def test_ev_all_queries_seen():
    """Verify all-queries-seen case returns next_query None and complete information reading."""
    from agent.loop import QUERY_FEATURES
    f = Features(queries_seen=set(QUERY_FEATURES.keys()))
    res = economics(0.0898, 0.0, f)
    assert res["next_query"] is None
    assert res["continue_gathering"] is False
    assert res["reading"] == "All evidence gathered \u2014 decision made on complete information."
