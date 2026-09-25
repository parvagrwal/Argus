"""Vector storage and retrieval for Argus fraud investigations (Requirement R1).

NON-NEGOTIABLE HONESTY BOUNDARY:
- Vector recall is INVESTIGATIVE CONTEXT for the narrative (R4-style), like a human
  analyst pulling prior cases for qualitative reference.
- It MUST NOT feed into agent/scoring.py features, weights, or probabilities.
- It MUST NOT count toward the Policy Section 6 two-evidence minimum. The `evidence`
  list is untouched.
- Results live in a separate `vector_context` field on Investigation, never in `evidence`.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("argus.vector_memory")

_MODEL: Any = None


def _get_embedding_model() -> Any:
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _MODEL


def _extract_case(it: dict[str, Any]) -> dict[str, str]:
    attrs = it.get("attributes", {}) if isinstance(it, dict) else {}
    cid = attrs.get("Res.case_id") or attrs.get("case_id") or it.get("v_id") or it.get("case_id", "")
    note = attrs.get("Res.note_text") or attrs.get("note_text") or it.get("note_text", "")
    outcome = attrs.get("Res.outcome") or attrs.get("outcome") or it.get("outcome", "")
    return {"case_id": str(cid), "note_text": str(note), "outcome": str(outcome)}


def recall_similar_cases(client: Any, query_text: str, k: int = 3) -> list[dict[str, Any]]:
    """Retrieve top-k semantically similar historical closed cases using TigerGraph vector search.

    Returns a list of dicts with keys: 'case_id', 'note_text', 'outcome'.
    Degrades gracefully: returns [] if the client has no vector support or if any error occurs.
    """
    if client is None:
        return []

    backend = getattr(client, "backend", "")

    # Mock client has no vector support: return [] immediately without loading any model
    if backend == "mock":
        return []

    # FixtureClient with recorded vector data
    if backend == "fixture":
        if hasattr(client, "get_vector_context"):
            return client.get_vector_context()
        try:
            res = client.run_query("vector_similar_cases")
            items = res.get("results", [{}])[0].get("similar_cases", [])
            return [_extract_case(it) for it in items][:k]
        except Exception:
            return []

    # Live TigerGraph client: lazy-load all-MiniLM-L6-v2 and call installed query
    try:
        model = _get_embedding_model()
        vec = model.encode(query_text, normalize_embeddings=True).tolist()
        res = client.run_query("vector_similar_cases", query_vector=vec, k=k)
        raw_items = res.get("results", [{}])[0].get("similar_cases", [])
        return [_extract_case(it) for it in raw_items][:k]
    except Exception as exc:
        log.warning("Vector recall failed gracefully: %s", exc)
        return []
