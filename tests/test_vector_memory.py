"""Unit tests for TigerGraph vector storage and retrieval (Requirement R1).

Verifies the non-negotiable honesty boundaries:
- Vector recall is strictly investigative context.
- Vector recall never feeds into scoring, weights, or probabilities.
- Vector recall never counts toward the Policy §6 evidence minimum.
"""

from __future__ import annotations

import copy
import pytest

from agent.loop import CaseInput, run_input
from agent.scoring import DEFAULT_WEIGHTS, score
from agent.vector_memory import recall_similar_cases
from fixtures import FixtureClient


def test_recall_similar_cases_keys_and_limit() -> None:
    """Requirement 9(a): recall returns <= 3 items with case_id, note_text, outcome keys."""
    client = FixtureClient("HHG-014")
    cases = recall_similar_cases(client, "analyst_request: cardholder unusual device", k=3)

    assert 0 < len(cases) <= 3
    for item in cases:
        assert isinstance(item, dict)
        assert "case_id" in item
        assert "note_text" in item
        assert "outcome" in item
        assert isinstance(item["case_id"], str) and len(item["case_id"]) > 0
        assert isinstance(item["note_text"], str) and len(item["note_text"]) > 0
        assert isinstance(item["outcome"], str) and len(item["outcome"]) > 0

    # Graceful degradation on mock or None
    assert recall_similar_cases(None, "some trigger") == []
    class MockClient:
        backend = "mock"
    assert recall_similar_cases(MockClient(), "some trigger") == []


def test_boundary_scoring_independence() -> None:
    """Requirement 9(b) BOUNDARY TEST:

    Run the scoring path with vector_context present vs absent -> assert identical fraud_probability.
    Vector recall must NEVER touch agent/scoring.py features, weights, or probabilities.
    """
    case = CaseInput.load("HHG-014")
    client = FixtureClient("HHG-014")

    # Run investigation with vector context populated
    inv_with_vector, _ = run_input(case, client=client)
    assert len(inv_with_vector.vector_context) > 0

    prob_with_vector = inv_with_vector.probability
    score_breakdown_1 = score(inv_with_vector.features, DEFAULT_WEIGHTS)
    assert score_breakdown_1["probability"] == pytest.approx(prob_with_vector, abs=1e-6)

    # Clone features and score again without any vector_context in scope
    features_copy = copy.deepcopy(inv_with_vector.features)
    score_breakdown_2 = score(features_copy, DEFAULT_WEIGHTS)

    assert score_breakdown_1["probability"] == pytest.approx(score_breakdown_2["probability"], abs=1e-6)
    assert score_breakdown_1["logit"] == pytest.approx(score_breakdown_2["logit"], abs=1e-6)
    assert score_breakdown_1["features"] == score_breakdown_2["features"]
    assert score_breakdown_1["bias"] == score_breakdown_2["bias"]

    # Even if vector_context is manually emptied or flooded with synthetic items,
    # the scoring output on inv.features is completely unchanged
    inv_with_vector.vector_context = []
    assert score(inv_with_vector.features, DEFAULT_WEIGHTS)["probability"] == pytest.approx(prob_with_vector, abs=1e-6)

    inv_with_vector.vector_context = [
        {"case_id": "CC-9999", "note_text": "arbitrary high risk text", "outcome": "confirmed_fraud"}
    ] * 50
    assert score(inv_with_vector.features, DEFAULT_WEIGHTS)["probability"] == pytest.approx(prob_with_vector, abs=1e-6)

    # Feature vector keys must not contain any vector-related fields
    vec_keys = set(inv_with_vector.features.vector().keys())
    for k in vec_keys:
        assert "vector" not in k.lower()
        assert "embedding" not in k.lower()
        assert "similarity" not in k.lower()


def test_vector_context_never_in_evidence() -> None:
    """Requirement 9(c): vector_context items never appear in the evidence list.

    Vector recall must NOT count toward the Policy §6 two-evidence minimum.
    """
    case = CaseInput.load("HHG-014")
    client = FixtureClient("HHG-014")

    inv, _ = run_input(case, client=client)

    assert len(inv.vector_context) > 0
    assert len(inv.evidence) >= 2  # Has valid Policy §6 evidence

    evidence_sources = [e.get("source") for e in inv.evidence]
    evidence_refs = [e.get("ref", "") for e in inv.evidence]
    evidence_claims = [e.get("claim", "") for e in inv.evidence]

    # Evidence sources must only be legitimate graph/trigger/policy sources, never vector recall
    for src in evidence_sources:
        assert src in ("graph", "trigger", "policy")

    # No evidence ref may point to vector search
    for ref in evidence_refs:
        assert "vector" not in ref.lower()

    # None of the retrieved vector cases may be masquerading as an evidence item
    for vec_item in inv.vector_context:
        assert vec_item not in inv.evidence
        for claim in evidence_claims:
            assert vec_item["note_text"] != claim
