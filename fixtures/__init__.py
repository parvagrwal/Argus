"""Recorded fixtures loader and FixtureClient for offline replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.trace import TraceRecorder

FIXTURES_DIR = Path(__file__).resolve().parent


def load(case_id: str, query_name: str) -> dict[str, Any]:
    """Load a recorded query response for a case."""
    path = FIXTURES_DIR / case_id / f"{query_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found for case {case_id!r} query {query_name!r} at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["response"]


class FixtureClient:
    """Offline graph client serving recorded query responses."""

    backend = "fixture"

    def __init__(self, case_id: str, trace: TraceRecorder | None = None):
        self.case_id = case_id
        self.trace = trace

    def run_query(self, name: str, **params: Any) -> dict[str, Any]:
        res = load(self.case_id, name)
        if self.trace is not None:
            with self.trace.timed(name, params, backend=self.backend) as slot:
                slot["result"] = res
        return res
