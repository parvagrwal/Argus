"""
TigerGraph access layer — REST++ fallback implementing the same tool interface the MCP tools
expose (AGENTS.md §1). P1.

Guarantees enforced here, not by convention:
  * ALLOW-LIST. A caller can invoke `get_schema` and the installed queries listed in
    ALLOWED_QUERIES (exactly the files in graph/queries/). Unknown query names, unknown
    parameters, missing required parameters and wrongly typed parameters raise
    `ToolNotAllowed` / `ParamError` before any network call.
  * NO ARBITRARY GSQL, NO DESTRUCTIVE OPERATIONS. The investigation client (`GraphClient`)
    has no method that accepts GSQL text. The setup-only `GraphAdmin` accepts GSQL for
    schema/query installation but refuses any text containing a destructive statement
    (graph/gsql_parse.DESTRUCTIVE_PATTERNS) and refuses upserts for types outside the schema.
  * OFFLINE FALLBACK. If TG credentials are missing or the Savanna workspace is unreachable,
    `get_client()` returns `MockGraphClient`, which enforces the same allow-list, records the
    same traces and returns responses stamped `"_mock": true` — never to be used as evidence
    in a submitted answer file.
  * NO SECRETS IN LOGS. Config `repr` redacts; errors never include headers or bodies with
    credentials; the trace redacts secret-like keys (mcp/trace.redact).

Endpoint layout targets TigerGraph Cloud 4.x (Savanna): `{host}/restpp/...` and
`{host}/gsql/v1/...` on the single HTTPS host. Paths are overridable via TG_RESTPP_PATH and
TG_GSQL_PATH for self-managed clusters.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from graph.gsql_parse import (
    DEFAULT_GRAPH,
    QUERIES_DIR,
    ParsedSchema,
    QuerySignature,
    find_destructive,
    load_query_files,
    parse_schema,
)
from mcp.trace import TraceRecorder

log = logging.getLogger("argus.graph")

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$")


class ToolNotAllowed(PermissionError):
    """Raised for any tool/query outside the allow-list or any destructive request."""


class ParamError(ValueError):
    """Raised when query parameters do not match the installed signature."""


class GraphUnavailable(ConnectionError):
    """Raised when the live backend cannot be reached."""


# --------------------------------------------------------------------------------------
# Allow-list — derived from the query files so it cannot drift from what is installed
# --------------------------------------------------------------------------------------

SCHEMA_TOOL = "get_schema"
ALLOWED_QUERIES: dict[str, QuerySignature] = load_query_files(QUERIES_DIR)
ALLOWED_TOOLS: frozenset[str] = frozenset({SCHEMA_TOOL, *ALLOWED_QUERIES})
READ_ONLY_QUERIES: frozenset[str] = frozenset(n for n in ALLOWED_QUERIES if n != "write_fraud_case")
WRITE_QUERIES: frozenset[str] = frozenset({"write_fraud_case"})


def _type_ok(gsql_type: str, value: Any) -> bool:
    t = gsql_type.upper()
    if t.startswith("VERTEX"):
        return isinstance(value, str) and value != ""
    if t == "STRING":
        return isinstance(value, str)
    if t in ("INT", "UINT"):
        return isinstance(value, int) and not isinstance(value, bool) and (t == "INT" or value >= 0)
    if t in ("DOUBLE", "FLOAT"):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "BOOL":
        return isinstance(value, bool)
    if t == "DATETIME":
        return isinstance(value, str) and bool(_DATETIME_RE.match(value))
    if t.startswith(("SET<", "BAG<", "LIST<")):
        inner = t[t.index("<") + 1 : -1]
        return isinstance(value, (list, tuple, set, frozenset)) and all(_type_ok(inner, v) for v in value)
    return False


def restpp_params(query: str, clean: dict[str, Any]) -> dict[str, Any]:
    """REST++ JSON body encoding of validated params: VERTEX<T> -> {"id": ..., "type": "T"}."""
    out: dict[str, Any] = {}
    for p in ALLOWED_QUERIES[query].params:
        if p.name not in clean:
            continue
        v = clean[p.name]
        m = re.match(r"VERTEX<(\w+)>", p.gsql_type)
        out[p.name] = {"id": v, "type": m.group(1)} if m else v
    return out


def validate_params(query: str, params: dict[str, Any]) -> dict[str, Any]:
    """Enforce the allow-list and the installed signature. Returns a JSON-ready param dict."""
    if query not in ALLOWED_QUERIES:
        raise ToolNotAllowed(f"query {query!r} is not in the allow-list {sorted(ALLOWED_QUERIES)}")
    sig = ALLOWED_QUERIES[query]
    declared = {p.name: p for p in sig.params}
    unknown = sorted(set(params) - set(declared))
    if unknown:
        raise ParamError(f"{query}: unknown parameter(s) {unknown}; allowed {sorted(declared)}")
    missing = [n for n in sig.required_params if n not in params]
    if missing:
        raise ParamError(f"{query}: missing required parameter(s) {missing}")
    clean: dict[str, Any] = {}
    for name, value in params.items():
        p = declared[name]
        if not _type_ok(p.gsql_type, value):
            raise ParamError(f"{query}: parameter {name!r} must be {p.gsql_type}, got {type(value).__name__}: {value!r}")
        if isinstance(value, (set, frozenset, tuple)):
            value = sorted(value)
        clean[name] = value
    return clean


# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------


@dataclass
class TGConfig:
    host: str = ""
    graph: str = DEFAULT_GRAPH
    username: str = ""
    password: str = field(default="", repr=False)
    secret: str = field(default="", repr=False)
    restpp_path: str = "/restpp"
    gsql_path: str = "/gsql"
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls, dotenv: bool = True) -> "TGConfig":
        if dotenv:
            try:
                from dotenv import load_dotenv

                load_dotenv(override=False)
            except Exception:  # pragma: no cover - dotenv optional
                pass
        return cls(
            host=os.getenv("TG_HOST", "").strip().rstrip("/"),
            graph=os.getenv("TG_GRAPHNAME", DEFAULT_GRAPH).strip() or DEFAULT_GRAPH,
            username=os.getenv("TG_USERNAME", "").strip(),
            password=os.getenv("TG_PASSWORD", ""),
            secret=os.getenv("TG_SECRET", ""),
            restpp_path=os.getenv("TG_RESTPP_PATH", "/restpp").strip() or "/restpp",
            gsql_path=os.getenv("TG_GSQL_PATH", "/gsql").strip() or "/gsql",
            timeout_s=float(os.getenv("TG_TIMEOUT_S", "60") or 60),
        )

    @property
    def configured(self) -> bool:
        placeholder = "your" in self.host.lower() or "your" in self.secret.lower() or "your" in self.password.lower()
        return bool(self.host) and (bool(self.secret) or (bool(self.username) and bool(self.password))) and not placeholder

    def __repr__(self) -> str:  # never leak credentials
        return (f"TGConfig(host={_redact_host(self.host)!r}, graph={self.graph!r}, username={'<set>' if self.username else ''!r}, "
                f"password={'<set>' if self.password else ''!r}, secret={'<set>' if self.secret else ''!r})")

    @property
    def restpp(self) -> str:
        return f"{self.host}{self.restpp_path}"

    @property
    def gsql(self) -> str:
        return f"{self.host}{self.gsql_path}"


def _redact_host(host: str) -> str:
    """Keep scheme + public suffix only (e.g. https://<workspace>.i.tgcloud.io)."""
    m = re.match(r"^(https?://)([^/]+)(/.*)?$", host)
    if not m:
        return "<host>" if host else ""
    labels = m.group(2).split(".")
    suffix = ".".join(labels[-3:]) if len(labels) > 3 else m.group(2)
    return f"{m.group(1)}<workspace>.{suffix}{m.group(3) or ''}"


# --------------------------------------------------------------------------------------
# Live client
# --------------------------------------------------------------------------------------


class GraphClient:
    """Investigation-side client: get_schema + allow-listed installed queries. Nothing else."""

    backend = "tigergraph"

    def __init__(self, config: TGConfig, trace: TraceRecorder | None = None, session: requests.Session | None = None):
        self.cfg = config
        self.trace = trace or TraceRecorder()
        self.http = session or requests.Session()
        self._token: str | None = None
        self._token_expiry = 0.0

    # -- auth ------------------------------------------------------------------------
    def _basic(self) -> tuple[str, str] | None:
        return (self.cfg.username, self.cfg.password) if self.cfg.username and self.cfg.password else None

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        tok = self._get_token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _get_token(self) -> str | None:
        if not self.cfg.secret:
            return None
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        attempts = [
            ("POST", f"{self.cfg.gsql}/v1/tokens", {"secret": self.cfg.secret, "graph": self.cfg.graph, "lifetime": 86400}),
            ("POST", f"{self.cfg.restpp}/requesttoken", {"secret": self.cfg.secret, "graph": self.cfg.graph, "lifetime": 86400}),
        ]
        for method, url, body in attempts:
            try:
                r = self.http.request(method, url, json=body, timeout=self.cfg.timeout_s, auth=self._basic())
                if r.ok:
                    data = r.json()
                    tok = data.get("token") or (data.get("results") or {}).get("token")
                    if tok:
                        self._token = tok
                        self._token_expiry = time.time() + 86400
                        return tok
            except requests.RequestException:
                continue
        log.warning("token request failed on all endpoints; falling back to basic auth")
        return None

    def _request(self, method: str, url: str, **kw: Any) -> Any:
        kw.setdefault("timeout", self.cfg.timeout_s)
        headers = {**self._headers(), **kw.pop("headers", {})}
        auth = None if "Authorization" in headers else self._basic()
        try:
            r = self.http.request(method, url, headers=headers, auth=auth, **kw)
        except requests.RequestException as exc:
            raise GraphUnavailable(f"{method} {_redact_host(url)}: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise GraphUnavailable(f"{method} {url.replace(self.cfg.host, _redact_host(self.cfg.host))} -> HTTP {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
        except ValueError:
            return {"raw": r.text}
        if isinstance(data, dict) and data.get("error") is True:
            raise GraphUnavailable(f"TigerGraph error: {str(data.get('message'))[:300]}")
        return data

    # -- health ----------------------------------------------------------------------
    def ping(self) -> dict[str, Any]:
        """GET /api/ping. Savanna returns 202 + 'Workspace ... is starting' while waking up."""
        try:
            r = self.http.get(f"{self.cfg.host}/api/ping", timeout=min(self.cfg.timeout_s, 15))
        except requests.RequestException as exc:
            raise GraphUnavailable(f"ping failed: {type(exc).__name__}") from exc
        body = r.text[:200]
        ready = r.status_code == 200 and "starting" not in body.lower()
        return {"status_code": r.status_code, "ready": ready, "message": body}

    def is_ready(self) -> bool:
        try:
            return self.ping()["ready"]
        except GraphUnavailable:
            return False

    # -- tools -----------------------------------------------------------------------
    def get_schema(self) -> dict[str, Any]:
        args = {"graph": self.cfg.graph}
        with self.trace.timed(SCHEMA_TOOL, args, backend=self.backend) as slot:
            last: Exception | None = None
            for url in (
                f"{self.cfg.gsql}/v1/schema/graphs/{self.cfg.graph}",
                f"{self.cfg.restpp}/gsqlserver/gsql/schema?graph={self.cfg.graph}",
                f"{self.cfg.host}/gsqlserver/gsql/schema?graph={self.cfg.graph}",
            ):
                try:
                    slot["result"] = self._request("GET", url)
                    return slot["result"]
                except GraphUnavailable as exc:
                    last = exc
            raise GraphUnavailable(f"get_schema failed on all endpoints: {last}")

    def run_query(self, name: str, **params: Any) -> dict[str, Any]:
        clean = validate_params(name, params)
        with self.trace.timed(name, clean, backend=self.backend) as slot:
            url = f"{self.cfg.restpp}/query/{self.cfg.graph}/{name}"
            slot["result"] = self._request("POST", url, json=restpp_params(name, clean),
                                           headers={"Content-Type": "application/json"})
            return slot["result"]

    def list_installed_queries(self) -> set[str]:
        data = self._request("GET", f"{self.cfg.restpp}/endpoints/{self.cfg.graph}?dynamic=true")
        names: set[str] = set()
        for key in (data.get("results") or data if isinstance(data, dict) else {}):
            m = re.search(rf"/query/{re.escape(self.cfg.graph)}/(\w+)", str(key))
            if m:
                names.add(m.group(1))
        return names


# --------------------------------------------------------------------------------------
# Setup-only admin client (graph/setup_graph.py). Still refuses destructive statements.
# --------------------------------------------------------------------------------------

_ALLOWED_GSQL_PREFIXES = (
    "CREATE GRAPH", "USE GRAPH", "USE GLOBAL", "CREATE SCHEMA_CHANGE JOB", "CREATE GLOBAL SCHEMA_CHANGE JOB",
    "RUN SCHEMA_CHANGE JOB", "RUN GLOBAL SCHEMA_CHANGE JOB", "CREATE QUERY", "CREATE OR REPLACE QUERY",
    "CREATE DISTRIBUTED QUERY", "CREATE OR REPLACE DISTRIBUTED QUERY", "INSTALL QUERY", "SHOW", "LS",
    "CREATE LOADING JOB", "RUN LOADING JOB", "SET",
)


class GraphAdmin(GraphClient):
    """Adds schema installation, query installation and batch upserts. No drops, ever."""

    def __init__(self, config: TGConfig, trace: TraceRecorder | None = None, schema: ParsedSchema | None = None,
                 session: requests.Session | None = None):
        super().__init__(config, trace, session)
        self.schema = schema or parse_schema()

    @staticmethod
    def guard_gsql(text: str) -> None:
        hits = find_destructive(text)
        if hits:
            raise ToolNotAllowed(f"destructive GSQL refused: {hits}")
        for stmt in _top_level_statements(text):
            head = stmt.upper()
            if not head.startswith(_ALLOWED_GSQL_PREFIXES):
                raise ToolNotAllowed(f"GSQL statement not in the setup allow-list: {stmt[:60]!r}")

    _GSQL_ERROR_MARKERS = ("syntax error", "semantic check fail", "encountered", "failed to", "access denied",
                           "does not exist", "is not allowed", "error:", "exception", "could not", "cannot",
                           "does not have", "permission", "denied", "aborted", "not installed")

    def run_gsql(self, text: str) -> dict[str, Any]:
        """POST GSQL text. Auth: the secret-derived bearer token first (it carries the roles of
        the account that created the secret and is scoped to TG_GRAPHNAME, so every statement
        must start with USE GRAPH), then basic auth as a fallback. GSQL answers in plain text;
        known error markers are turned into GraphUnavailable so a broken query or schema
        statement can never pass silently."""
        self.guard_gsql(text)
        tok = self._get_token()
        auth_modes: list[dict[str, Any]] = []
        if tok:
            auth_modes.append({"headers": {"Authorization": f"Bearer {tok}"}})
        if self._basic():
            auth_modes.append({"auth": self._basic()})
        if not auth_modes:
            raise GraphUnavailable("run_gsql needs TG_SECRET or TG_USERNAME/TG_PASSWORD")
        with self.trace.timed("gsql", {"chars": len(text), "head": text.strip().splitlines()[0][:80]},
                              agent="setup", backend=self.backend) as slot:
            last: Exception | None = None
            for url, mode in [(u, m) for m in auth_modes for u in (f"{self.cfg.gsql}/v1/statements", f"{self.cfg.host}/gsqlserver/gsql/file")]:
                try:
                    r = self.http.post(url, data=text.encode("utf-8"), auth=mode.get("auth"),
                                       headers={"Content-Type": "text/plain", "Accept": "application/json", **mode.get("headers", {})},
                                       timeout=max(self.cfg.timeout_s, 600))
                except requests.RequestException as exc:
                    last = GraphUnavailable(f"gsql POST: {type(exc).__name__}")
                    continue
                if r.status_code >= 400:
                    last = GraphUnavailable(f"gsql -> HTTP {r.status_code}: {r.text[:400]}")
                    continue
                body = r.text
                try:
                    data = r.json()
                    if isinstance(data, dict):
                        if data.get("error"):
                            raise GraphUnavailable(f"gsql error: {str(data.get('message'))[:600]}")
                        body = json.dumps(data.get("results", data)) if not isinstance(data.get("results"), str) else data["results"]
                except ValueError:
                    pass
                low = body.lower()
                if any(m in low for m in self._GSQL_ERROR_MARKERS):
                    raise GraphUnavailable(f"gsql reported an error: {body[:1200]}")
                slot["result"] = {"raw": body}
                return slot["result"]
            raise GraphUnavailable(f"run_gsql failed on all endpoints: {last}")

    def upsert(self, vertices: dict[str, dict[str, dict[str, Any]]] | None = None,
               edges: list[tuple[str, str, str, str, str, dict[str, Any]]] | None = None) -> dict[str, Any]:
        """POST /restpp/graph/{graph}. Only schema-declared types are accepted.

        vertices: {vtype: {vid: {attr: value}}}
        edges:    [(src_type, src_id, edge_type, tgt_type, tgt_id, {attr: value}), ...]
        """
        payload: dict[str, Any] = {}
        if vertices:
            for vtype, rows in vertices.items():
                if vtype not in self.schema.vertices:
                    raise ToolNotAllowed(f"upsert refused: vertex type {vtype!r} not in schema")
                payload.setdefault("vertices", {})[vtype] = {
                    vid: {k: {"value": v} for k, v in attrs.items()} for vid, attrs in rows.items()
                }
        if edges:
            e_out = payload.setdefault("edges", {})
            for src_t, src_id, etype, tgt_t, tgt_id, attrs in edges:
                if etype not in self.schema.edges:
                    raise ToolNotAllowed(f"upsert refused: edge type {etype!r} not in schema")
                e_out.setdefault(src_t, {}).setdefault(src_id, {}).setdefault(etype, {}).setdefault(tgt_t, {})[tgt_id] = {
                    k: {"value": v} for k, v in (attrs or {}).items()
                }
        if not payload:
            return {"accepted_vertices": 0, "accepted_edges": 0}
        with self.trace.timed("upsert", {"vertex_types": list((vertices or {}).keys()), "n_edges": len(edges or [])},
                              agent="setup", backend=self.backend) as slot:
            slot["result"] = self._request("POST", f"{self.cfg.restpp}/graph/{self.cfg.graph}", json=payload,
                                           headers={"Content-Type": "application/json"})
            return slot["result"]

    def counts(self, exact_vertices: bool = True) -> dict[str, int]:
        """Vertex and edge counts by type. `stat_*` builtins are approximate/eventually consistent
        right after a load, so vertex counts default to the exact `count_only` endpoint."""
        out: dict[str, int] = {}
        for fn in ("stat_vertex_number", "stat_edge_number"):
            data = self._request("POST", f"{self.cfg.restpp}/builtins/{self.cfg.graph}", json={"function": fn, "type": "*"})
            for row in data.get("results", []):
                key = row.get("v_type") or row.get("e_type")
                if key:
                    out[key] = int(row.get("count", 0))
        if exact_vertices:
            for vtype in self.schema.vertices:
                try:
                    data = self._request("GET", f"{self.cfg.restpp}/graph/{self.cfg.graph}/vertices/{vtype}?count_only=true")
                    res = data.get("results")
                    if isinstance(res, list) and res and isinstance(res[0], dict) and "count" in res[0]:
                        out[vtype] = int(res[0]["count"])
                    elif isinstance(res, dict) and "count" in res:
                        out[vtype] = int(res["count"])
                except GraphUnavailable:
                    pass
        return out

    def graph_exists(self) -> bool:
        try:
            self.get_schema()
            return True
        except GraphUnavailable:
            return False


def _top_level_statements(text: str) -> list[str]:
    """Split GSQL into statements. A job / query body (inside braces or parentheses) belongs to its header; a
    depth-0 line starting with a continuation keyword (FOR GRAPH, SYNTAX, WITH, RETURNS, API)
    continues the previous statement; any other depth-0 line starts a new one."""
    from graph.gsql_parse import strip_comments

    continuation = {"FOR", "SYNTAX", "WITH", "RETURNS", "API", "{", "}"}
    body = strip_comments(text)
    out: list[list[str]] = []
    depth = 0
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        first = s.split(None, 1)[0].upper().rstrip("{(")
        if depth == 0 and (first not in continuation) and not s.startswith(("{", "}")):
            out.append([s])
        elif out:
            out[-1].append(s)
        else:
            out.append([s])
        depth += s.count("{") - s.count("}") + s.count("(") - s.count(")")
    return [" ".join(parts) for parts in out]


# --------------------------------------------------------------------------------------
# Offline mock / dry-run client — same interface, same allow-list, clearly labelled
# --------------------------------------------------------------------------------------


class MockGraphClient:
    """Structural stand-in used when TigerGraph is unreachable or for offline tests.

    Every response carries `"_mock": True`. Results are EMPTY by design: a mock must never
    look like evidence (AGENTS.md §1). Optional recorded fixtures (real query outputs saved
    under graph/fixtures/<query>/<key>.json) can be served when present, labelled `_fixture`.
    """

    backend = "mock"

    def __init__(self, config: TGConfig | None = None, trace: TraceRecorder | None = None,
                 fixtures_dir: Path | None = None):
        self.cfg = config or TGConfig()
        self.trace = trace or TraceRecorder()
        self.schema = parse_schema()
        self.fixtures_dir = fixtures_dir
        self.written_cases: dict[str, dict[str, Any]] = {}  # in-memory write-back for tests
        log.warning("TigerGraph not available: MockGraphClient in use. Mock results are NOT evidence.")

    def ping(self) -> dict[str, Any]:
        return {"status_code": 0, "ready": False, "message": "mock backend", "_mock": True}

    def is_ready(self) -> bool:
        return False

    def get_schema(self) -> dict[str, Any]:
        with self.trace.timed(SCHEMA_TOOL, {"graph": self.cfg.graph}, backend=self.backend) as slot:
            slot["result"] = {
                "_mock": True,
                "GraphName": self.cfg.graph,
                "VertexTypes": [{"Name": v.name, "PrimaryId": v.primary_id, "Attributes": v.attributes}
                                for v in self.schema.vertices.values()],
                "EdgeTypes": [{"Name": e.name, "FromVertexTypeName": e.from_type, "ToVertexTypeName": e.to_type,
                               "IsDirected": e.directed, "ReverseEdge": e.reverse_edge}
                              for e in self.schema.edges.values()],
            }
            return slot["result"]

    def run_query(self, name: str, **params: Any) -> dict[str, Any]:
        clean = validate_params(name, params)
        with self.trace.timed(name, clean, backend=self.backend) as slot:
            fixture = self._fixture(name, clean)
            if fixture is not None:
                slot["result"] = fixture
                return fixture
            if name == "write_fraud_case":
                self.written_cases[clean["graph_case_id"]] = dict(clean)
                result = {"_mock": True, "version": {"schema": 0}, "error": False, "results": [
                    {"graph_case_id": clean["graph_case_id"], "case_id": clean["case_id"], "card_id": clean["card_id"],
                     "card_found": False, "n_txn_edges": 0, "n_device_edges": 0, "n_prior_edges": 0},
                    {"txns_not_found": sorted(clean.get("affected_txn_ids", []))},
                    {"devices_not_found": sorted(clean.get("device_profiles", []))},
                    {"priors_not_found": sorted(clean.get("prior_case_ids", []))},
                ]}
            elif name == "get_case_with_evidence":
                stored = self.written_cases.get(clean["graph_case_id"])
                result = {"_mock": True, "error": False, "results": [
                    {"found": 1 if stored else 0},
                    {"investigation_case": [
                        {"v_id": stored["graph_case_id"], "v_type": "InvestigationCase",
                         "attributes": {k: stored[k] for k in ("graph_case_id", "case_id", "status", "verdict",
                                                                 "fraud_probability", "pattern", "exposure_usd",
                                                                 "summary", "payload_json")}}
                    ] if stored else []},
                    {"card_ids": []}, {"affected_txn_ids": []}, {"device_profiles": []}, {"prior_case_ids": []},
                ]}
            else:
                result = {"_mock": True, "error": False, "results": []}
            slot["result"] = result
            return result

    def _fixture(self, name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self.fixtures_dir:
            return None
        key = re.sub(r"[^A-Za-z0-9_.-]", "_", json.dumps(params, sort_keys=True))[:150]
        path = self.fixtures_dir / name / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_fixture"] = str(path.relative_to(self.fixtures_dir))
            return data
        return None


# --------------------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------------------


def get_client(trace: TraceRecorder | None = None, force_mock: bool = False,
               config: TGConfig | None = None) -> GraphClient | MockGraphClient:
    """Live client when credentials exist and the workspace answers; otherwise the mock."""
    cfg = config or TGConfig.from_env()
    if force_mock or os.getenv("ARGUS_FORCE_MOCK", "").lower() in {"1", "true", "yes"}:
        return MockGraphClient(cfg, trace)
    if not cfg.configured:
        log.warning("TG credentials missing or placeholders in .env; using mock backend")
        return MockGraphClient(cfg, trace)
    live = GraphClient(cfg, trace)
    if live.is_ready():
        return live
    log.warning("TigerGraph workspace not ready (%r); using mock backend", cfg)
    return MockGraphClient(cfg, trace)
