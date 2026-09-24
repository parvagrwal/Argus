"""
Tiny GSQL text helpers shared by graph/setup_graph.py, mcp/fallback_rest.py and the tests.

This is NOT a GSQL parser. It extracts, with regexes, exactly what Argus needs:
  * vertex / edge type declarations from graph/schema.gsql
  * the query name and parameter signature from graph/queries/*.gsql
  * a destructive-statement check used to refuse dangerous GSQL
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "graph" / "schema.gsql"
QUERIES_DIR = ROOT / "graph" / "queries"
DEFAULT_GRAPH = "FraudInvestigation"

# Any of these makes a GSQL text destructive. Matched case-insensitively on word boundaries.
DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    r"\bDROP\s+(ALL|GRAPH|VERTEX|EDGE|QUERY|JOB|TUPLE|DATA_SOURCE|USER|ROLE|SECRET|TOKEN|INDEX|GLOBAL)\b",
    r"\bDROP\b",
    r"\bCLEAR\s+GRAPH\s+STORE\b",
    r"\bDELETE\b",
    r"\bTRUNCATE\b",
    r"\bABORT\s+LOADING\b",
    r"\bREVOKE\b",
    r"\bALTER\s+PASSWORD\b",
    r"\bGRANT\b",
    r"\bCREATE\s+(USER|SECRET|TOKEN)\b",
    r"\bEXPORT\s+GRAPH\b",
    r"\bIMPORT\s+GRAPH\b",
    r"\bCLEAR\b",
)

_COMMENT_RE = re.compile(r"//[^\n]*|#[^\n]*|/\*.*?\*/", re.S)


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def find_destructive(text: str) -> list[str]:
    """Return the destructive keywords found in `text` (after removing comments)."""
    body = strip_comments(text)
    hits: list[str] = []
    for pat in DESTRUCTIVE_PATTERNS:
        for m in re.finditer(pat, body, flags=re.I):
            hits.append(m.group(0).upper())
    return sorted(set(hits))


# --------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------

_VERTEX_RE = re.compile(r"ADD\s+VERTEX\s+(\w+)\s*\((.*?)\)\s*WITH", re.S | re.I)
_EDGE_RE = re.compile(
    r"ADD\s+(DIRECTED|UNDIRECTED)\s+EDGE\s+(\w+)\s*\(\s*FROM\s+(\w+)\s*,\s*TO\s+(\w+)(.*?)\)\s*(?:WITH\s+REVERSE_EDGE\s*=\s*\"(\w+)\")?\s*;",
    re.S | re.I,
)
_ATTR_RE = re.compile(r"(?:PRIMARY_ID\s+)?(\w+)\s+(STRING|INT|UINT|DOUBLE|FLOAT|BOOL|DATETIME)", re.I)


@dataclass
class VertexType:
    name: str
    primary_id: str
    attributes: dict[str, str] = field(default_factory=dict)  # name -> type (upper)


@dataclass
class EdgeType:
    name: str
    from_type: str
    to_type: str
    directed: bool
    reverse_edge: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedSchema:
    graph: str
    vertices: dict[str, VertexType]
    edges: dict[str, EdgeType]

    def edge_names_with_reverse(self) -> set[str]:
        names = set(self.edges)
        names |= {e.reverse_edge for e in self.edges.values() if e.reverse_edge}
        return names


def parse_schema(text: str | None = None) -> ParsedSchema:
    raw = text if text is not None else SCHEMA_FILE.read_text(encoding="utf-8")
    body = strip_comments(raw)
    graph = DEFAULT_GRAPH
    m = re.search(r"CREATE\s+GRAPH\s+(\w+)", body, re.I)
    if m:
        graph = m.group(1)
    vertices: dict[str, VertexType] = {}
    for vm in _VERTEX_RE.finditer(body):
        name, attrs_txt = vm.group(1), vm.group(2)
        attrs: dict[str, str] = {}
        primary = ""
        for am in _ATTR_RE.finditer(attrs_txt):
            attrs[am.group(1)] = am.group(2).upper()
        pm = re.search(r"PRIMARY_ID\s+(\w+)", attrs_txt, re.I)
        if pm:
            primary = pm.group(1)
        vertices[name] = VertexType(name=name, primary_id=primary, attributes=attrs)
    edges: dict[str, EdgeType] = {}
    for em in _EDGE_RE.finditer(body):
        kind, name, frm, to, attr_txt, rev = em.groups()
        attrs = {am.group(1): am.group(2).upper() for am in _ATTR_RE.finditer(attr_txt or "")}
        edges[name] = EdgeType(name=name, from_type=frm, to_type=to, directed=kind.upper() == "DIRECTED",
                               reverse_edge=rev or "", attributes=attrs)
    return ParsedSchema(graph=graph, vertices=vertices, edges=edges)


# --------------------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------------------

_QUERY_HEAD_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:DISTRIBUTED\s+)?QUERY\s+(\w+)\s*\((.*?)\)\s*FOR\s+GRAPH\s+(\w+)",
    re.S | re.I,
)
_PARAM_RE = re.compile(
    r"\s*(VERTEX<\w+>|SET<\w+>|BAG<\w+>|LIST<\w+>|STRING|INT|UINT|DOUBLE|FLOAT|BOOL|DATETIME|VERTEX)\s+(\w+)(?:\s*=\s*([^,]+))?\s*$",
    re.I,
)


@dataclass
class QueryParam:
    name: str
    gsql_type: str          # e.g. "VERTEX<Card>", "DATETIME", "SET<STRING>"
    default: str | None     # literal text of default or None (=> required)

    @property
    def required(self) -> bool:
        return self.default is None


@dataclass
class QuerySignature:
    name: str
    graph: str
    params: list[QueryParam]
    file: Path | None = None

    @property
    def param_names(self) -> list[str]:
        return [p.name for p in self.params]

    @property
    def required_params(self) -> list[str]:
        return [p.name for p in self.params if p.required]


def parse_query(text: str, file: Path | None = None) -> QuerySignature:
    body = strip_comments(text)
    m = _QUERY_HEAD_RE.search(body)
    if not m:
        raise ValueError(f"no CREATE QUERY header found in {file or '<text>'}")
    name, params_txt, graph = m.group(1), m.group(2), m.group(3)
    params: list[QueryParam] = []
    for raw in _split_params(params_txt):
        if not raw.strip():
            continue
        pm = _PARAM_RE.match(raw)
        if not pm:
            raise ValueError(f"cannot parse parameter {raw!r} in {name}")
        gtype, pname, default = pm.group(1), pm.group(2), pm.group(3)
        params.append(QueryParam(name=pname, gsql_type=_normalise_type(gtype), default=default.strip() if default else None))
    return QuerySignature(name=name, graph=graph, params=params, file=file)


def _normalise_type(t: str) -> str:
    t = t.strip()
    inner = re.match(r"(\w+)<(\w+)>", t)
    if inner:
        return f"{inner.group(1).upper()}<{inner.group(2)}>"
    return t.upper()


def _split_params(txt: str) -> list[str]:
    """Split on commas not inside <> (SET<STRING>) — params never contain other commas."""
    out, depth, cur = [], 0, []
    for ch in txt:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def load_query_files(directory: Path | None = None) -> dict[str, QuerySignature]:
    d = directory or QUERIES_DIR
    out: dict[str, QuerySignature] = {}
    for f in sorted(d.glob("*.gsql")):
        sig = parse_query(f.read_text(encoding="utf-8"), file=f)
        out[sig.name] = sig
    return out


def referenced_types(query_text: str) -> tuple[set[str], set[str]]:
    """Vertex types and edge types referenced by a query body (best effort)."""
    body = strip_comments(query_text)
    vertex_types: set[str] = set()
    edge_types: set[str] = set()
    for m in re.finditer(r"VERTEX<(\w+)>", body):
        vertex_types.add(m.group(1))
    for m in re.finditer(r"\{\s*(\w+)\.\*\s*\}", body):
        vertex_types.add(m.group(1))
    for m in re.finditer(r"-\s*\(\s*(\w+)\s*>?\s*:?\s*\w*\s*\)\s*-\s*(\w+)\s*:", body):
        edge_types.add(m.group(1))
        vertex_types.add(m.group(2))
    for m in re.finditer(r"INSERT\s+INTO\s+(\w+)", body, re.I):
        vertex_types.add(m.group(1)) if m.group(1)[0].isupper() and not m.group(1).isupper() else edge_types.add(m.group(1))
    for m in re.finditer(r"VALUES\s*\(.*?\b(\w+)\s+([A-Z][A-Za-z]+)\s*\)", body, re.S):
        vertex_types.add(m.group(2))
    for m in re.finditer(r"outdegree\(\"(\w+)\"\)", body):
        edge_types.add(m.group(1))
    return vertex_types, edge_types


def balanced(text: str) -> bool:
    body = strip_comments(text)
    body = re.sub(r'"(?:\\.|[^"\\])*"', '""', body)
    for open_ch, close_ch in (("{", "}"), ("(", ")"), ("[", "]")):
        if body.count(open_ch) != body.count(close_ch):
            return False
    return True
