"""
Call instrumentation for every graph / retrieval tool call — P1.

Design (AGENTS.md §1, D-08):
  * Every tool call is recorded as a `ToolCall` (agent/schema.py) in an internal trace.
  * The official answer file gets ONLY the integer `tool_calls` count (plus tokens and
    latency_s); the detailed trace lives in `InternalCaseRecord.tool_trace`.
  * Arguments are redacted before recording: anything that looks like a secret is replaced,
    and long values are truncated. Nothing here ever prints a credential.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from agent.schema import ToolCall

_SECRET_MARKERS = ("secret", "password", "passwd", "token", "api_key", "apikey", "authorization")
_MAX_ARG_CHARS = 400


def redact(value: Any, key: str = "") -> Any:
    """Redact secrets and truncate long values; safe for logs and traces."""
    lowered = key.lower()
    if any(m in lowered for m in _SECRET_MARKERS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [redact(v) for v in value]
        return items if len(items) <= 50 else items[:50] + [f"<+{len(items) - 50} more>"]
    if isinstance(value, str) and len(value) > _MAX_ARG_CHARS:
        return value[:_MAX_ARG_CHARS] + f"<+{len(value) - _MAX_ARG_CHARS} chars>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)[:_MAX_ARG_CHARS]


def count_rows(result: Any) -> int:
    """Best-effort row count for a REST++ result: sum of list lengths in `results`."""
    if result is None:
        return 0
    payload = result.get("results", result) if isinstance(result, dict) else result
    total = 0
    if isinstance(payload, list):
        for block in payload:
            if isinstance(block, dict):
                for v in block.values():
                    if isinstance(v, list):
                        total += len(v)
                    elif isinstance(v, dict):
                        total += len(v)
                    else:
                        total += 1
            else:
                total += 1
    elif isinstance(payload, dict):
        total = len(payload)
    return total


@dataclass
class TraceEvent:
    step: int
    agent: str
    tool: str
    args: dict[str, Any]
    rows: int
    latency_ms: float
    ts: str
    ok: bool = True
    error: str = ""
    backend: str = "unknown"  # "tigergraph" | "mock"

    def to_tool_call(self) -> ToolCall:
        return ToolCall(step=self.step, agent=self.agent, tool=self.tool, args=self.args,
                        rows=self.rows, latency_ms=self.latency_ms, ts=self.ts)


@dataclass
class TraceRecorder:
    """Collects TraceEvents for one case. Thread-unsafe by design (one recorder per case)."""

    case_id: str = ""
    events: list[TraceEvent] = field(default_factory=list)

    # -- recording -------------------------------------------------------------------
    def record(self, tool: str, args: dict[str, Any] | None, rows: int, latency_ms: float,
               agent: str = "graph", ok: bool = True, error: str = "", backend: str = "unknown") -> TraceEvent:
        ev = TraceEvent(
            step=len(self.events) + 1,
            agent=agent,
            tool=tool,
            args=redact(dict(args or {})),
            rows=int(rows),
            latency_ms=round(float(latency_ms), 3),
            ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            ok=ok,
            error=redact(error) if error else "",
            backend=backend,
        )
        self.events.append(ev)
        return ev

    @contextmanager
    def timed(self, tool: str, args: dict[str, Any] | None = None, agent: str = "graph",
              backend: str = "unknown") -> Iterator[dict[str, Any]]:
        """Usage: with rec.timed("card_window", params) as slot: slot["result"] = call()."""
        slot: dict[str, Any] = {"result": None}
        t0 = time.perf_counter()
        try:
            yield slot
        except Exception as exc:  # record then re-raise; failed calls still count
            self.record(tool, args, 0, (time.perf_counter() - t0) * 1000, agent=agent,
                        ok=False, error=f"{type(exc).__name__}: {exc}", backend=backend)
            raise
        self.record(tool, args, count_rows(slot["result"]), (time.perf_counter() - t0) * 1000,
                    agent=agent, backend=backend)

    # -- official / internal views --------------------------------------------------
    @property
    def tool_calls(self) -> int:
        """The ONLY thing the official answer file sees from this trace."""
        return len(self.events)

    @property
    def latency_s(self) -> float:
        return round(sum(e.latency_ms for e in self.events) / 1000.0, 3)

    def to_tool_trace(self) -> list[ToolCall]:
        """InternalCaseRecord.tool_trace — never written into cases/<id>.json."""
        return [e.to_tool_call() for e in self.events]

    def official_counts(self) -> dict[str, Any]:
        """Exactly the top-level answer-file fields this module is allowed to fill."""
        return {"tool_calls": self.tool_calls, "latency_s": self.latency_s}

    def backends_used(self) -> set[str]:
        return {e.backend for e in self.events}

    def to_json(self) -> str:
        return json.dumps([e.__dict__ for e in self.events], indent=2, default=str)
