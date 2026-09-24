"""Unit tests for agent/counterfactual.py — Deterministic counterfactual explanation generator."""

from __future__ import annotations

import math
import pytest

from agent.counterfactual import counterfactual
from agent.scoring import DEFAULT_WEIGHTS, Features


def test_counterfactual_binary_flip():
    """Synthetic fraud case where flipping one binary feature crosses 0.85 boundary."""
    # Probability 0.86, just above 0.85 boundary. Flipping new_device (w=1.1) crosses boundary.
    weights = {"new_device": 1.1}
    features = Features(new_device=1.0)
    p = 0.86

    cf = counterfactual(features, weights, 0.0, p, "fraud")

    assert cf["flips"] is True
    assert cf["feature"] == "new_device"
    assert cf["new_probability"] < 0.85
    assert "new_device" in cf["sentence"]
    assert "crossing the 0.85 decision boundary" in cf["sentence"]


def test_counterfactual_no_flip():
    """No single feature flip can bridge extreme probability -> robustness sentence."""
    features = Features(risk_score=0.99, new_device=1.0, online=1.0)
    p = 0.9999

    cf = counterfactual(features, DEFAULT_WEIGHTS, -1.6, p, "fraud")

    assert cf["flips"] is False
    expected_sentence = "No single evidence change flips this decision \u2014 the verdict is robust to any one feature."
    assert cf["sentence"] == expected_sentence


def test_counterfactual_uncertain_raises():
    """Verdict 'uncertain' must raise AssertionError."""
    features = Features(risk_score=0.50)
    with pytest.raises(AssertionError):
        counterfactual(features, DEFAULT_WEIGHTS, -1.6, 0.50, "uncertain")


def test_counterfactual_log_feature():
    """A *_log feature case reports integer counts, not raw log units."""
    weights = {"prior_fraud_log": 0.9}
    # 3 prior frauds: log1p(3) = 1.3863
    features = {"prior_fraud_log": math.log1p(3)}
    # Choose probability such that need / 0.9 yields a delta between 0 and 1.3863
    # logit(0.85) = 1.734601; let logit = 1.734601 + 0.18 = 1.914601
    p = 1.0 / (1.0 + math.exp(-1.914601))

    cf = counterfactual(features, weights, 0.0, p, "fraud")

    assert cf["flips"] is True
    assert cf["feature"] == "prior_fraud_log"
    # Sentence reports 'prior fraud' and counts (e.g. 2 instead of 3), not '_log'
    assert "prior fraud" in cf["sentence"]
    assert "_log" not in cf["sentence"]
    assert "instead of 3" in cf["sentence"]
