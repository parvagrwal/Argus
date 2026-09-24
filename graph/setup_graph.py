"""
graph/setup_graph.py — create the schema, install the queries and batch-load the graph. P1.

    python -m graph.setup_graph --dry-run            # no network: derive card IDs, validate, count
    python -m graph.setup_graph --schema --queries   # live: non-destructive schema + query install
    python -m graph.setup_graph --load [--limit N]   # live: batch upserts (only needed columns)
    python -m graph.setup_graph --verify             # live: counts + read-only smoke queries
    python -m graph.setup_graph --all                # schema, queries, load, verify

Rules honoured here (AGENTS.md §1, §9, §10):
  * Only the columns needed by the installed queries are read; CSVs are chunk-read with
    explicit `usecols`. The 397-column transactions file is never loaded whole.
  * Card IDs come from graph/card_id.py and are validated against the labelled files BEFORE
    any graph write. A material mismatch aborts the load.
  * Nothing is ever dropped. Schema changes are ADD-only for types that do not exist yet;
    queries are CREATE OR REPLACE; loads are upserts.
  * Credentials come from .env via mcp.fallback_rest.TGConfig and are never printed.
  * Unnamed model features (V*, C*, D*, M*, id_01…id_14, id_16…id_22, id_24…id_29, id_32,
    id_35…id_38) are NOT loaded. Only the human-readable identity fields are (id_15, id_23,
    id_30, id_31, id_33, id_34, DeviceType, DeviceInfo), and the queries say what they are.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

from graph.card_id import (
    CardMap,
    ValidationReport,
    assign_card_ids,
    build_card_map_from_csv,
    derive_txn_card_ids,
    iter_transaction_chunks,
    validate_against_labels,
)
from graph.gsql_parse import QUERIES_DIR, ROOT, SCHEMA_FILE, ParsedSchema, parse_schema, strip_comments

log = logging.getLogger("argus.setup")

DATA = ROOT / "data"
TRANSACTIONS_CSV = DATA / "transactions.csv"
IDENTITY_CSV = DATA / "identity.csv"
CLOSED_CASES_CSV = DATA / "closed_cases_history.csv"
CASE_PACK_CSV = DATA / "case_pack.csv"
DERIVED_DIR = DATA / "derived"

# Exactly the transaction columns the installed queries need (see graph/schema.gsql comments).
TXN_COLUMNS: tuple[str, ...] = (
    "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD", "card6", "addr1", "addr2",
    "P_emaildomain", "R_emaildomain", "customer_id", "ts", "channel", "risk_score",
)
IDENTITY_COLUMNS: tuple[str, ...] = (
    "TransactionID", "id_15", "id_23", "id_30", "id_31", "id_33", "id_34", "DeviceType", "DeviceInfo",
)
HOME_COUNTRY_CODE = "87"


# --------------------------------------------------------------------------------------
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------------------


def clean_str(value: Any) -> str:
    """NaN/None/'nan' -> ''; floats that are whole numbers -> '444' (addr codes)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        return str(int(value)) if value.is_integer() else str(value)
    if value is pd.NA:
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"nan", "<na>", "none"} else s


def make_device_profile(device_info: Any, os_: Any, browser: Any, screen: Any) -> str:
    """README connected_device_profiles format: 'DeviceInfo | OS | browser | screen'.
    Returns '' when every component is blank (no profile -> no DeviceProfile vertex)."""
    parts = [clean_str(device_info), clean_str(os_), clean_str(browser), clean_str(screen)]
    if not any(parts):
        return ""
    return " | ".join(parts)


@dataclass
class Batch:
    vertices: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    edges: list[tuple[str, str, str, str, str, dict[str, Any]]] = field(default_factory=list)

    def vertex(self, vtype: str, vid: str, **attrs: Any) -> None:
        self.vertices.setdefault(vtype, {})[vid] = attrs

    def edge(self, src_t: str, src_id: str, etype: str, tgt_t: str, tgt_id: str, **attrs: Any) -> None:
        self.edges.append((src_t, src_id, etype, tgt_t, tgt_id, attrs))

    @property
    def n_vertices(self) -> int:
        return sum(len(v) for v in self.vertices.values())

    @property
    def n_edges(self) -> int:
        return len(self.edges)


def transactions_to_batch(chunk: pd.DataFrame, card_map: CardMap, identity: dict[str, dict[str, str]]) -> Batch:
    """Turn a chunk of transactions.csv (TXN_COLUMNS) + identity lookup into vertices/edges."""
    b = Batch()
    card_ids = assign_card_ids(chunk, card_map)
    for row, card_id in zip(chunk.itertuples(index=False), card_ids):
        tid = str(row.TransactionID)
        ident = identity.get(tid, {})
        profile = make_device_profile(ident.get("DeviceInfo"), ident.get("id_30"), ident.get("id_31"), ident.get("id_33"))
        addr1, addr2 = clean_str(row.addr1), clean_str(row.addr2)
        p_email, r_email = clean_str(row.P_emaildomain), clean_str(row.R_emaildomain)
        b.vertex(
            "Transaction", tid,
            transaction_dt=int(row.TransactionDT),
            amount=float(row.TransactionAmt),
            product_cd=clean_str(row.ProductCD),
            channel=clean_str(row.channel),
            ts=clean_str(row.ts),
            risk_score=float(row.risk_score),
            addr1=addr1,
            addr2=addr2,
            card_id=str(card_id),
            customer_id=clean_str(row.customer_id),
            p_emaildomain=p_email,
            r_emaildomain=r_email,
            device_status=clean_str(ident.get("id_15")),
            proxy_flag=clean_str(ident.get("id_23")),
            device_type=clean_str(ident.get("DeviceType")),
            match_status=clean_str(ident.get("id_34")),
            device_profile=profile,
        )
        b.edge("Transaction", tid, "TRANS_ON_CARD", "Card", str(card_id))
        if profile:
            b.vertex("DeviceProfile", profile, device_info=clean_str(ident.get("DeviceInfo")), os=clean_str(ident.get("id_30")),
                     browser=clean_str(ident.get("id_31")), screen=clean_str(ident.get("id_33")))
            b.edge("Transaction", tid, "HAS_DEVICE", "DeviceProfile", profile)
        if p_email:
            b.vertex("EmailDomain", p_email)
            b.edge("Transaction", tid, "USES_EMAIL", "EmailDomain", p_email)
        if r_email:
            b.vertex("EmailDomain", r_email)
            b.edge("Transaction", tid, "RECIPIENT_EMAIL", "EmailDomain", r_email)
        if addr1:
            b.vertex("BillingRegion", addr1)
            b.edge("Transaction", tid, "BILLED_IN", "BillingRegion", addr1)
    return b


def cards_to_batch(card_map: CardMap) -> Batch:
    b = Batch()
    for card_id, customer_id, card6, k in card_map.rows():
        b.vertex("Customer", customer_id)
        b.vertex("Card", card_id, customer_id=customer_id, card6=card6, k_index=k)
        b.edge("Customer", customer_id, "OWNS_CARD", "Card", card_id)
    return b


def closed_cases_to_batch(closed: pd.DataFrame, known_txns: set[str] | None, known_cards: set[str]) -> Batch:
    """closed_cases_history.csv rows -> ClosedCase vertices + PRIOR_CASE_ON / CASE_INCLUDES_TXN /
    CASE_CONNECTED_CARD edges. Edges are only created to IDs that exist (no fabricated vertices)."""
    b = Batch()
    for row in closed.itertuples(index=False):
        cid = str(row.case_id)
        b.vertex(
            "ClosedCase", cid,
            customer_id=clean_str(row.customer_id), card_id=clean_str(row.card_id),
            opened_at=clean_str(row.opened_at), closed_at=clean_str(row.closed_at),
            outcome=clean_str(row.outcome), pattern=clean_str(row.pattern),
            first_fraud_txn_id=clean_str(row.first_fraud_txn_id), n_txns=int(row.n_txns),
            exposure_usd=float(row.exposure_usd), actions_taken=clean_str(row.actions_taken),
            report_filed=clean_str(row.report_filed).lower() == "yes", analyst_notes=clean_str(row.analyst_notes),
        )
        if clean_str(row.card_id) in known_cards:
            b.edge("ClosedCase", cid, "PRIOR_CASE_ON", "Card", clean_str(row.card_id))
        for tid in filter(None, clean_str(row.txn_ids).split("|")):
            if known_txns is None or tid in known_txns:
                b.edge("ClosedCase", cid, "CASE_INCLUDES_TXN", "Transaction", tid)
        for cc in filter(None, clean_str(row.connected_card_ids).split("|")):
            if cc in known_cards:
                b.edge("ClosedCase", cid, "CASE_CONNECTED_CARD", "Card", cc)
    return b


def load_identity(path: Path = IDENTITY_CSV) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for chunk in pd.read_csv(path, usecols=list(IDENTITY_COLUMNS), chunksize=50_000, dtype=str):
        for row in chunk.itertuples(index=False):
            out[str(row.TransactionID)] = {c: clean_str(getattr(row, c)) for c in IDENTITY_COLUMNS[1:]}
    return out


def split_batches(b: Batch, max_vertices: int) -> Iterator[Batch]:
    """Split a Batch so each request carries at most ~max_vertices Transaction rows worth."""
    if b.n_vertices <= max_vertices:
        yield b
        return
    if "Transaction" not in b.vertices:
        # Dimension-only batch (cards, closed cases): vertices first, then edges, in slices.
        for vtype, rows in b.vertices.items():
            items = list(rows.items())
            for i in range(0, len(items), max_vertices):
                part = Batch()
                part.vertices = {vtype: dict(items[i : i + max_vertices])}
                yield part
        for i in range(0, len(b.edges), max_vertices * 4):
            part = Batch()
            part.edges = list(b.edges[i : i + max_vertices * 4])
            yield part
        return
    # Split by Transaction ids; the small dimension vertices are re-sent per part (upsert is idempotent).
    txns = list(b.vertices.get("Transaction", {}).items())
    dims = {k: v for k, v in b.vertices.items() if k != "Transaction"}
    edges_by_src: dict[str, list] = {}
    for e in b.edges:
        edges_by_src.setdefault(e[1], []).append(e)
    for i in range(0, len(txns), max_vertices):
        part = Batch()
        part.vertices = {k: dict(v) for k, v in dims.items()}
        part.vertices["Transaction"] = dict(txns[i : i + max_vertices])
        for tid, _ in txns[i : i + max_vertices]:
            part.edges.extend(edges_by_src.get(tid, []))
        yield part


# --------------------------------------------------------------------------------------
# Sinks: dry-run counter vs live GraphAdmin
# --------------------------------------------------------------------------------------


class DryRunSink:
    """Counts what would be upserted. Never touches the network."""

    backend = "dry-run"

    def __init__(self) -> None:
        self.vertex_ids: dict[str, set[str]] = {}
        self.edge_counts: dict[str, int] = {}
        self.requests = 0

    def upsert(self, vertices=None, edges=None) -> dict[str, Any]:
        self.requests += 1
        for vtype, rows in (vertices or {}).items():
            self.vertex_ids.setdefault(vtype, set()).update(rows)
        for e in edges or []:
            self.edge_counts[e[2]] = self.edge_counts.get(e[2], 0) + 1
        return {"dry_run": True}

    def counts(self) -> dict[str, int]:
        out = {k: len(v) for k, v in self.vertex_ids.items()}
        out.update(self.edge_counts)
        return out


ACCEPTED: dict[str, int] = {"accepted_vertices": 0, "accepted_edges": 0, "skipped_vertices": 0, "skipped_edges": 0}


def _tally(response: Any) -> None:
    """Aggregate REST++ upsert responses ({"results":[{"accepted_vertices":..}]}) into ACCEPTED."""
    rows = response.get("results", []) if isinstance(response, dict) else []
    for row in rows if isinstance(rows, list) else [rows]:
        if isinstance(row, dict):
            for k in ACCEPTED:
                if isinstance(row.get(k), int):
                    ACCEPTED[k] += row[k]
            for k in ("vertices_skipped", "edges_skipped"):  # alternate spellings across versions
                if isinstance(row.get(k), int):
                    ACCEPTED["skipped_vertices" if k.startswith("vert") else "skipped_edges"] += row[k]


def push(sink: Any, batch: Batch, max_vertices: int) -> int:
    n = 0
    for part in split_batches(batch, max_vertices):
        _tally(sink.upsert(vertices=part.vertices, edges=part.edges))
        n += 1
    return n


# --------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------


def step_derive(write_csv: bool = True) -> tuple[CardMap, dict[str, str], ValidationReport]:
    t0 = time.time()
    card_map = build_card_map_from_csv(TRANSACTIONS_CSV)
    txn_card = derive_txn_card_ids(TRANSACTIONS_CSV, card_map)
    report = validate_against_labels(txn_card, card_map, CLOSED_CASES_CSV, CASE_PACK_CSV)
    log.info("card derivation: %d cards / %d customers in %.1fs; material mismatch=%s",
             card_map.n_cards, card_map.n_customers, time.time() - t0, report.material)
    if write_csv:
        DERIVED_DIR.mkdir(parents=True, exist_ok=True)
        card_map.to_frame().sort_values("card_id").to_csv(DERIVED_DIR / "card_ids.csv", index=False)
        (DERIVED_DIR / "card_id_validation.json").write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    if report.material:
        raise SystemExit(f"card-id derivation has material mismatches; refusing to load: {report.as_dict()}")
    return card_map, txn_card, report


def render_schema_job(schema: ParsedSchema, existing_vertices: set[str], existing_edges: set[str], graph: str) -> str:
    """ADD-only schema change job for the types that are missing on the cluster."""
    body = strip_comments(SCHEMA_FILE.read_text(encoding="utf-8"))
    adds: list[str] = []
    import re

    for m in re.finditer(r"ADD\s+VERTEX\s+(\w+)\s*\(.*?\)\s*WITH[^;]*;", body, re.S):
        if m.group(1) not in existing_vertices:
            adds.append(re.sub(r"\s+", " ", m.group(0)).strip())
    for m in re.finditer(r"ADD\s+(?:DIRECTED|UNDIRECTED)\s+EDGE\s+(\w+)\s*\(.*?\)\s*(?:WITH[^;]*)?;", body, re.S):
        if m.group(1) not in existing_edges:
            adds.append(re.sub(r"\s+", " ", m.group(0)).strip())
    if not adds:
        return ""
    job = f"argus_p1_schema_{int(time.time())}"
    lines = [f"USE GRAPH {graph}", f"CREATE SCHEMA_CHANGE JOB {job} FOR GRAPH {graph} {{"]
    lines += [f"  {a}" for a in adds]
    lines += ["}", f"RUN SCHEMA_CHANGE JOB {job}"]
    return "\n".join(lines) + "\n"


def _names(schema_json: dict[str, Any], key: str) -> set[str]:
    data = schema_json.get("results", schema_json) if isinstance(schema_json, dict) else {}
    items = data.get(key, []) if isinstance(data, dict) else []
    return {it.get("Name") for it in items if isinstance(it, dict) and it.get("Name")}


def step_schema(admin: Any) -> dict[str, Any]:
    schema = parse_schema()
    graph = admin.cfg.graph
    existing_v: set[str] = set()
    existing_e: set[str] = set()
    created_graph = False
    try:
        live = admin.get_schema()
        existing_v, existing_e = _names(live, "VertexTypes"), _names(live, "EdgeTypes")
    except Exception as exc:  # graph missing -> create it (non-destructive)
        log.info("graph %s not found (%s); creating", graph, type(exc).__name__)
        admin.run_gsql(f"CREATE GRAPH {graph} ()\n")
        created_graph = True
    job = render_schema_job(schema, existing_v, existing_e, graph)
    if job:
        admin.run_gsql(job)
    return {"created_graph": created_graph, "added_types": job.count("ADD "), "existing_vertices": sorted(existing_v),
            "existing_edges": sorted(existing_e)}


def step_queries(admin: Any) -> dict[str, Any]:
    graph = admin.cfg.graph
    names: list[str] = []
    for f in sorted(QUERIES_DIR.glob("*.gsql")):
        text = f.read_text(encoding="utf-8").replace("FOR GRAPH FraudInvestigation", f"FOR GRAPH {graph}")
        admin.run_gsql(f"USE GRAPH {graph}\n{text}\n")
        names.append(f.stem)
    admin.run_gsql(f"USE GRAPH {graph}\nINSTALL QUERY {', '.join(names)}\n")
    return {"installed": names}


def step_load(sink: Any, card_map: CardMap, txn_card: dict[str, str], limit: int | None, batch_rows: int,
              chunk_rows: int = 50_000) -> dict[str, Any]:
    t0 = time.time()
    stats: dict[str, Any] = {"requests": 0, "transactions": 0}
    stats["requests"] += push(sink, cards_to_batch(card_map), batch_rows * 4)
    identity = load_identity() if IDENTITY_CSV.exists() else {}
    stats["identity_rows"] = len(identity)
    loaded_txns: set[str] = set()
    remaining = limit
    for chunk in iter_transaction_chunks(TRANSACTIONS_CSV, TXN_COLUMNS, chunk_rows):
        if remaining is not None:
            if remaining <= 0:
                break
            chunk = chunk.head(remaining)
            remaining -= len(chunk)
        batch = transactions_to_batch(chunk, card_map, identity)
        stats["requests"] += push(sink, batch, batch_rows)
        stats["transactions"] += len(chunk)
        loaded_txns.update(chunk["TransactionID"].astype(str))
        log.info("loaded %d transactions (%.0fs)", stats["transactions"], time.time() - t0)
    closed = pd.read_csv(CLOSED_CASES_CSV, dtype=str)
    known_txns = loaded_txns if limit is not None else None
    stats["requests"] += push(sink, closed_cases_to_batch(closed, known_txns, card_map.all_card_ids()), batch_rows * 4)
    stats["closed_cases"] = len(closed)
    stats["seconds"] = round(time.time() - t0, 1)
    stats["server_accepted"] = dict(ACCEPTED)
    return stats


def step_verify(admin: Any, expected: dict[str, int] | None = None) -> dict[str, Any]:
    """Read-only: counts by type, schema fetch, installed queries, one smoke query per read-only
    query on the README example card, and get_case_with_evidence on a non-existent id."""
    from mcp.fallback_rest import GraphClient

    out: dict[str, Any] = {"counts": admin.counts()}
    if expected:
        out["count_mismatches"] = {k: (v, out["counts"].get(k)) for k, v in expected.items() if out["counts"].get(k) != v}
    out["installed_queries"] = sorted(admin.list_installed_queries())
    client = GraphClient(admin.cfg, admin.trace)
    pack = pd.read_csv(CASE_PACK_CSV, dtype=str)
    row = pack.iloc[0]
    card = row["card_id"]
    end = row["opened_at"]
    start = (pd.Timestamp(end) - pd.Timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    smoke: dict[str, Any] = {}
    for name, params in (
        ("card_window", {"card": card, "window_start": start, "window_end": end, "max_rows": 50}),
        ("velocity_check", {"card": card, "window_start": start, "window_end": end}),
        ("device_neighbors", {"card": card, "window_start": start, "window_end": end}),
        ("detect_fraud_ring", {"card": card, "window_start": start, "window_end": end, "max_hops": 2}),
        ("region_profile", {"card": card, "flagged_region": "444", "window_start": start, "window_end": end}),
        ("get_case_with_evidence", {"graph_case_id": "ARGUS-DOES-NOT-EXIST"}),
    ):
        try:
            res = client.run_query(name, **params)
            smoke[name] = {"ok": True, "blocks": len(res.get("results", []))}
        except Exception as exc:
            smoke[name] = {"ok": False, "error": str(exc)[:200]}
    out["smoke_queries"] = smoke
    out["tool_calls_traced"] = admin.trace.tool_calls
    return out


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="derive + validate + count; no network")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--queries", action="store_true")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="load only the first N transactions")
    ap.add_argument("--batch", type=int, default=2000, help="transactions per upsert request")
    ap.add_argument("--wait", type=int, default=0, help="seconds to wait for the workspace to wake up")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)  # urllib3 DEBUG would print the workspace host

    if args.all:
        args.schema = args.queries = args.load = args.verify = True
    if not any((args.dry_run, args.schema, args.queries, args.load, args.verify)):
        ap.print_help()
        return 2

    summary: dict[str, Any] = {}

    if args.dry_run:
        if not TRANSACTIONS_CSV.exists():
            print(json.dumps({"error": f"{TRANSACTIONS_CSV.name} not present (not committed; see data/INVENTORY.md)"}))
            return 1
        card_map, txn_card, report = step_derive()
        sink = DryRunSink()
        load_stats = step_load(sink, card_map, txn_card, args.limit, args.batch)
        summary = {"mode": "dry-run", "card_id_validation": report.as_dict(), "load": load_stats, "would_load": sink.counts()}
        (DERIVED_DIR / "dry_run_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    from mcp.fallback_rest import GraphAdmin, GraphUnavailable, TGConfig

    cfg = TGConfig.from_env()
    if not cfg.configured:
        print("TG credentials missing in .env (see .env.example). Use --dry-run for offline mode.", file=sys.stderr)
        return 1
    admin = GraphAdmin(cfg)
    deadline = time.time() + args.wait
    while not admin.is_ready():
        if time.time() >= deadline:
            print(f"workspace not ready: {admin.ping() if args.verbose else 'use --wait N to wait for wake-up'}", file=sys.stderr)
            return 1
        time.sleep(15)
    summary["config"] = repr(cfg)

    try:
        if args.schema:
            summary["schema"] = step_schema(admin)
        if args.queries:
            summary["queries"] = step_queries(admin)
        expected = None
        if args.load:
            card_map, txn_card, report = step_derive()
            summary["card_id_validation"] = report.as_dict()
            dry = DryRunSink()
            summary["load"] = step_load(admin, card_map, txn_card, args.limit, args.batch)
            if args.limit is None:
                step_load(dry, card_map, txn_card, None, args.batch)
                expected = dry.counts()
        if args.verify:
            summary["verify"] = step_verify(admin, expected)
    except GraphUnavailable as exc:
        summary["error"] = str(exc)
        print(json.dumps(summary, indent=2, default=str))
        return 1
    summary["tool_calls_traced"] = admin.trace.tool_calls
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
