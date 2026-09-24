"""GSQL schema/query hygiene, the access-layer allow-list, destructive-op guard, offline mock
and trace capture. Everything here runs without network access."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd
import pytest

from agent.schema import ToolCall
from graph import gsql_parse as gp
from graph import setup_graph as sg
from graph.card_id import build_card_map
from mcp import fallback_rest as fr
from mcp.trace import TraceRecorder, redact

SCHEMA_TEXT = gp.SCHEMA_FILE.read_text(encoding="utf-8")
QUERY_FILES = sorted(gp.QUERIES_DIR.glob("*.gsql"))
EXPECTED_QUERIES = {
    "card_window", "velocity_check", "device_neighbors", "detect_fraud_ring",
    "region_profile", "write_fraud_case", "get_case_with_evidence",
}


# ------------------------------------------------------------------ schema.gsql


def test_schema_parses_and_has_expected_types():
    s = gp.parse_schema(SCHEMA_TEXT)
    assert s.graph == "FraudInvestigation"
    assert set(s.vertices) == {
        "Customer", "Card", "Transaction", "DeviceProfile", "EmailDomain", "BillingRegion",
        "ClosedCase", "InvestigationCase",
    }
    assert {"OWNS_CARD", "TRANS_ON_CARD", "HAS_DEVICE", "USES_EMAIL", "RECIPIENT_EMAIL", "BILLED_IN",
            "PRIOR_CASE_ON"} <= set(s.edges)
    for e in s.edges.values():
        assert e.from_type in s.vertices and e.to_type in s.vertices, e
        assert e.reverse_edge, f"{e.name} needs a reverse edge for traversals"


def test_schema_has_no_ip_or_merchant_and_is_add_only():
    body = gp.strip_comments(SCHEMA_TEXT)
    assert not re.search(r"\bVERTEX\s+(IP|Merchant|IPAddress)\b", body, re.I)
    assert not re.search(r"\b(USES_IP|AT_MERCHANT|SIMILAR_TO|FLAGGED_BY)\b", body)
    assert gp.find_destructive(SCHEMA_TEXT) == []
    assert "ADD VERTEX" in body and "CREATE VERTEX" not in body  # schema-change job, never global CREATE
    fr.GraphAdmin.guard_gsql(SCHEMA_TEXT)  # must be accepted by the setup guard


def test_every_transaction_attribute_traces_to_a_real_column():
    # Real columns per data/INVENTORY.md headers (transactions.csv / identity.csv) + the two derived fields.
    mapping = {
        "txn_id": "TransactionID", "transaction_dt": "TransactionDT", "amount": "TransactionAmt",
        "product_cd": "ProductCD", "channel": "channel", "ts": "ts", "risk_score": "risk_score",
        "addr1": "addr1", "addr2": "addr2", "card_id": "<derived card6 rank>", "customer_id": "customer_id",
        "p_emaildomain": "P_emaildomain", "r_emaildomain": "R_emaildomain", "device_status": "id_15",
        "proxy_flag": "id_23", "device_type": "DeviceType", "match_status": "id_34",
        "device_profile": "<derived DeviceInfo|id_30|id_31|id_33>",
    }
    s = gp.parse_schema(SCHEMA_TEXT)
    assert set(s.vertices["Transaction"].attributes) == set(mapping)
    real_cols = set(sg.TXN_COLUMNS) | set(sg.IDENTITY_COLUMNS)
    for attr, col in mapping.items():
        assert col.startswith("<derived") or col in real_cols, (attr, col)


# ------------------------------------------------------------------ queries


def test_query_files_are_exactly_the_implemented_set():
    assert {f.stem for f in QUERY_FILES} == EXPECTED_QUERIES


@pytest.mark.parametrize("path", QUERY_FILES, ids=[p.stem for p in QUERY_FILES])
def test_query_header_and_syntax_basics(path: Path):
    text = path.read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:25])
    for tag in ("// Query:", "// Algorithm:", "// Pattern:", "// Columns:"):
        assert tag in head, f"{path.name} missing header line {tag}"
    sig = gp.parse_query(text, path)
    assert sig.name == path.stem, "query name must equal file name"
    assert sig.graph == "FraudInvestigation"
    assert "CREATE OR REPLACE QUERY" in text, "queries must be re-installable without DROP"
    assert "SYNTAX v2" in text
    assert gp.balanced(text), f"{path.name} has unbalanced brackets"
    assert gp.strip_comments(text).rstrip().endswith("}")
    assert gp.find_destructive(text) == [], gp.find_destructive(text)
    # every query must return something
    assert "PRINT" in text


@pytest.mark.parametrize("path", QUERY_FILES, ids=[p.stem for p in QUERY_FILES])
def test_query_references_only_schema_types(path: Path):
    s = gp.parse_schema(SCHEMA_TEXT)
    vt, et = gp.referenced_types(path.read_text(encoding="utf-8"))
    assert vt <= set(s.vertices), vt - set(s.vertices)
    assert et <= s.edge_names_with_reverse(), et - s.edge_names_with_reverse()


@pytest.mark.parametrize("path", QUERY_FILES, ids=[p.stem for p in QUERY_FILES])
def test_query_attribute_references_exist(path: Path):
    """t.attr / d.attr style references must be real attributes or vertex-attached accumulators."""
    s = gp.parse_schema(SCHEMA_TEXT)
    body = gp.strip_comments(path.read_text(encoding="utf-8"))
    body = re.sub(r'"[^"]*"', '""', body)
    all_attrs = {a for v in s.vertices.values() for a in v.attributes}
    for m in re.finditer(r"\b([a-z]\w*)\.([a-z_]\w*)\b", body):
        alias, attr = m.group(1), m.group(2)
        if alias in {"window_start", "window_end"} or attr in {"size", "get", "contains", "containsKey", "outdegree"}:
            continue
        # tuple field access on @@sorted.get(i).x is allowed; skip method chains
        if body[m.start() - 1 : m.start()] == ")":
            continue
        assert attr in all_attrs or attr.startswith("@"), f"{path.name}: unknown attribute {alias}.{attr}"


def test_write_query_never_creates_target_vertices_blindly():
    text = gp.strip_comments((gp.QUERIES_DIR / "write_fraud_case.gsql").read_text(encoding="utf-8"))
    # Edge inserts only iterate over sets that were resolved from existing vertices.
    for m in re.finditer(r"FOREACH\s+x\s+IN\s+(@@\w+)\s+DO\s+INSERT", text):
        assert m.group(1).endswith("_found"), m.group(0)
    assert "INSERT INTO Transaction" not in text and "INSERT INTO Card" not in text
    assert "INSERT INTO InvestigationCase" in text
    assert "txns_not_found" in text and "devices_not_found" in text and "priors_not_found" in text


# ------------------------------------------------------------------ allow-list & params


def test_allow_list_is_exactly_schema_plus_query_files():
    assert set(fr.ALLOWED_QUERIES) == EXPECTED_QUERIES
    assert fr.ALLOWED_TOOLS == EXPECTED_QUERIES | {"get_schema"}
    assert fr.WRITE_QUERIES == {"write_fraud_case"}
    assert fr.READ_ONLY_QUERIES == EXPECTED_QUERIES - {"write_fraud_case"}


def test_allow_list_params_match_gsql_signatures():
    for name, sig in fr.ALLOWED_QUERIES.items():
        on_disk = gp.parse_query((gp.QUERIES_DIR / f"{name}.gsql").read_text(encoding="utf-8"))
        assert [(p.name, p.gsql_type, p.default) for p in sig.params] == [
            (p.name, p.gsql_type, p.default) for p in on_disk.params
        ]


GOOD = {"card": "C00377-K1", "window_start": "2016-11-14 00:00:00", "window_end": "2016-11-15 00:00:00"}


def test_validate_params_accepts_good_and_fills_nothing():
    clean = fr.validate_params("card_window", {**GOOD, "max_rows": 20})
    assert clean == {**GOOD, "max_rows": 20}


@pytest.mark.parametrize(
    "query,params,exc",
    [
        ("drop_everything", {}, fr.ToolNotAllowed),
        ("get_schema", {}, fr.ToolNotAllowed),  # get_schema is a tool, not a query
        ("card_window", {"card": "C1"}, fr.ParamError),  # missing required
        ("card_window", {**GOOD, "evil": 1}, fr.ParamError),  # unknown param
        ("card_window", {**GOOD, "window_start": "2016-11-14"}, fr.ParamError),  # bad DATETIME
        ("card_window", {**GOOD, "max_rows": "20"}, fr.ParamError),  # wrong type
        ("card_window", {**GOOD, "max_rows": True}, fr.ParamError),  # bool is not INT
        ("detect_fraud_ring", {**GOOD, "include_email": "yes"}, fr.ParamError),
        ("write_fraud_case", {"graph_case_id": "X"}, fr.ParamError),
        ("card_window", {**GOOD, "card": ""}, fr.ParamError),
    ],
)
def test_validate_params_rejects(query, params, exc):
    with pytest.raises(exc):
        fr.validate_params(query, params)


def test_validate_params_set_types_become_sorted_lists():
    clean = fr.validate_params(
        "write_fraud_case",
        dict(graph_case_id="G", case_id="HHG-001", card_id="C1-K1", status="open", verdict="uncertain",
             fraud_probability=0.4, pattern="none", exposure_usd=0.0, summary="s",
             affected_txn_ids={"b", "a"}, device_profiles=(), prior_case_ids=["CC-1"], payload_json="{}"),
    )
    assert clean["affected_txn_ids"] == ["a", "b"] and clean["device_profiles"] == []


# ------------------------------------------------------------------ destructive guard


@pytest.mark.parametrize(
    "text",
    [
        "DROP GRAPH FraudInvestigation",
        "DROP ALL",
        "USE GRAPH FraudInvestigation\nDROP QUERY card_window",
        "CLEAR GRAPH STORE -HARD",
        "USE GRAPH g\nCREATE QUERY q() FOR GRAPH g { S = {Card.*}; DELETE s FROM S:s; }",
        "USE GRAPH g\nDROP VERTEX Card",
        "GRANT ROLE admin ON GRAPH g TO bob",
        "CREATE SECRET",
        "SELECT * FROM Card",  # not destructive but not in the setup allow-list either
        "RUN LOADING JOB x  -- fine --\nDROP JOB x",
    ],
)
def test_guard_refuses(text):
    with pytest.raises(fr.ToolNotAllowed):
        fr.GraphAdmin.guard_gsql(text)


def test_guard_accepts_setup_statements():
    fr.GraphAdmin.guard_gsql("CREATE GRAPH FraudInvestigation ()")
    fr.GraphAdmin.guard_gsql("USE GRAPH FraudInvestigation\nINSTALL QUERY card_window, velocity_check")
    for p in QUERY_FILES:
        fr.GraphAdmin.guard_gsql("USE GRAPH FraudInvestigation\n" + p.read_text(encoding="utf-8"))


def test_investigation_client_has_no_gsql_or_destructive_methods():
    public = {n for n in dir(fr.GraphClient) if not n.startswith("_")}
    assert "run_gsql" not in public and "upsert" not in public
    assert not any(re.search(r"drop|delete|clear|truncate", n, re.I) for n in dir(fr.GraphAdmin))


def test_upsert_refuses_types_outside_schema():
    admin = fr.GraphAdmin(fr.TGConfig(host="https://example.invalid", secret="x"))
    with pytest.raises(fr.ToolNotAllowed):
        admin.upsert(vertices={"Merchant": {"m1": {}}})
    with pytest.raises(fr.ToolNotAllowed):
        admin.upsert(edges=[("Transaction", "1", "USES_IP", "IP", "1.2.3.4", {})])
    assert admin.upsert() == {"accepted_vertices": 0, "accepted_edges": 0}  # empty is a no-op, no network


def test_render_schema_job_is_add_only_and_skips_existing():
    s = gp.parse_schema(SCHEMA_TEXT)
    job = sg.render_schema_job(s, {"Customer", "Card"}, {"OWNS_CARD"}, "FraudInvestigation")
    assert "ADD VERTEX Customer" not in job and "ADD VERTEX Transaction" in job
    assert "ADD DIRECTED EDGE OWNS_CARD" not in job and "ADD DIRECTED EDGE TRANS_ON_CARD" in job
    assert gp.find_destructive(job) == []
    fr.GraphAdmin.guard_gsql(job)
    full = sg.render_schema_job(s, set(s.vertices), set(s.edges), "FraudInvestigation")
    assert full == ""  # nothing to do when everything exists


# ------------------------------------------------------------------ mock backend & trace


def test_get_client_force_mock_needs_no_network(monkeypatch):
    monkeypatch.setenv("ARGUS_FORCE_MOCK", "1")
    c = fr.get_client()
    assert isinstance(c, fr.MockGraphClient)


def test_get_client_without_credentials_returns_mock(monkeypatch):
    monkeypatch.delenv("ARGUS_FORCE_MOCK", raising=False)
    cfg = fr.TGConfig(host="", secret="")
    c = fr.get_client(config=cfg)
    assert isinstance(c, fr.MockGraphClient)
    cfg2 = fr.TGConfig(host="https://your-sentinel-subdomain.i.tgcloud.io", secret="your_generated_secret_key_here")
    assert not cfg2.configured  # .env.example placeholders never count as configured


def test_mock_enforces_allow_list_and_labels_results():
    rec = TraceRecorder(case_id="HHG-001")
    m = fr.MockGraphClient(trace=rec)
    with pytest.raises(fr.ToolNotAllowed):
        m.run_query("select_star")
    with pytest.raises(fr.ParamError):
        m.run_query("card_window", card="C1")
    res = m.run_query("card_window", **GOOD)
    assert res["_mock"] is True and res["results"] == []
    schema = m.get_schema()
    assert schema["_mock"] is True and {v["Name"] for v in schema["VertexTypes"]} >= {"Card", "Transaction"}
    assert rec.tool_calls == 2  # failed validations are not tool calls; 1 query + 1 schema fetch


def test_mock_write_then_readback_roundtrip():
    m = fr.MockGraphClient()
    payload = json.dumps({"case_id": "HHG-001", "case": {"summary": "x"}}, sort_keys=True)
    w = m.run_query(
        "write_fraud_case", graph_case_id="ARGUS-HHG-001-1", case_id="HHG-001", card_id="C00377-K1", status="open",
        verdict="uncertain", fraud_probability=0.5, pattern="none", exposure_usd=0.0, summary="s",
        affected_txn_ids={"3514030"}, device_profiles=set(), prior_case_ids=set(), payload_json=payload,
    )
    assert w["_mock"] and w["results"][0]["graph_case_id"] == "ARGUS-HHG-001-1"
    r = m.run_query("get_case_with_evidence", graph_case_id="ARGUS-HHG-001-1")
    assert r["results"][0]["found"] == 1
    assert r["results"][1]["investigation_case"][0]["attributes"]["payload_json"] == payload
    missing = m.run_query("get_case_with_evidence", graph_case_id="nope")
    assert missing["results"][0]["found"] == 0


def test_trace_capture_matches_schema_and_official_count():
    rec = TraceRecorder(case_id="HHG-017")
    m = fr.MockGraphClient(trace=rec)
    m.get_schema()
    m.run_query("card_window", **GOOD)
    m.run_query("velocity_check", **GOOD)
    with pytest.raises(fr.ParamError):
        m.run_query("card_window", card="bad")  # rejected before the trace: not a call
    assert rec.tool_calls == 3
    trace = rec.to_tool_trace()
    assert all(isinstance(t, ToolCall) for t in trace)
    assert [t.step for t in trace] == [1, 2, 3]
    assert [t.tool for t in trace] == ["get_schema", "card_window", "velocity_check"]
    assert trace[1].args == GOOD
    assert rec.official_counts() == {"tool_calls": 3, "latency_s": rec.latency_s}
    assert isinstance(rec.official_counts()["tool_calls"], int)
    assert rec.backends_used() == {"mock"}
    json.loads(rec.to_json())


def test_trace_records_failed_calls_and_reraises():
    rec = TraceRecorder()
    with pytest.raises(RuntimeError):
        with rec.timed("card_window", GOOD, backend="tigergraph"):
            raise RuntimeError("boom")
    assert rec.tool_calls == 1 and rec.events[0].ok is False and "boom" in rec.events[0].error


def test_redaction_and_config_repr_never_leak_secrets(caplog):
    cfg = fr.TGConfig(host="https://tg-abc123.tg-999.i.tgcloud.io", username="parv", password="p4ss-w0rd!",
                      secret="sup3rs3cret")
    text = repr(cfg)
    for leak in ("p4ss-w0rd!", "sup3rs3cret", "tg-abc123", "tg-999"):
        assert leak not in text
    assert "<set>" in text and "<workspace>" in text
    red = redact({"secret": "abc", "TG_PASSWORD": "x", "Authorization": "Bearer t", "card": "C1", "long": "z" * 1000})
    assert red["secret"] == red["TG_PASSWORD"] == red["Authorization"] == "<redacted>"
    assert red["card"] == "C1" and red["long"].endswith("<+600 chars>")
    rec = TraceRecorder()
    rec.record("write_fraud_case", {"payload_json": "{}", "api_key": "k"}, 0, 1.0)
    assert rec.events[0].args["api_key"] == "<redacted>"
    with caplog.at_level(logging.WARNING):
        fr.MockGraphClient(cfg)
    assert "p4ss-w0rd!" not in caplog.text and "sup3rs3cret" not in caplog.text


# ------------------------------------------------------------------ load helpers (pure)


def test_clean_str_and_device_profile():
    assert sg.clean_str(444.0) == "444" and sg.clean_str(float("nan")) == "" and sg.clean_str(" a ") == "a"
    assert sg.clean_str(0.61) == "0.61" and sg.clean_str(None) == ""
    assert sg.make_device_profile("SM-G935F Build/NRD90M", "Android 7.0", "chrome 62.0 for android", "1920x1080") == \
        "SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080"
    assert sg.make_device_profile(None, float("nan"), "", None) == ""  # all-blank -> no vertex
    assert sg.make_device_profile(None, None, "firefox 47.0", None) == " |  | firefox 47.0 | "


def test_transactions_to_batch_uses_only_real_columns_and_skips_blank_dimensions():
    chunk = pd.DataFrame(
        {
            "TransactionID": [1, 2], "TransactionDT": [86400, 86500], "TransactionAmt": [77.07, 292.36],
            "ProductCD": ["W", "C"], "card6": ["debit", "debit"], "addr1": [444.0, float("nan")],
            "addr2": [87.0, float("nan")], "P_emaildomain": ["gmail.com", None], "R_emaildomain": [None, "anonymous.com"],
            "customer_id": ["C09999", "C09999"], "ts": ["2016-12-04 19:55:28", "2016-12-04 20:00:00"],
            "channel": ["in_person", "online"], "risk_score": [0.61, 0.79],
        }
    )
    cm = build_card_map([("C09999", "debit")])
    identity = {"2": {"id_15": "New", "id_23": "IP_PROXY:ANONYMOUS", "id_30": "Android 7.0", "id_31": "chrome 62.0 for android",
                      "id_33": "1920x1080", "id_34": "match_status:2", "DeviceType": "mobile", "DeviceInfo": "SM-G935F Build/NRD90M"}}
    b = sg.transactions_to_batch(chunk, cm, identity)
    t1, t2 = b.vertices["Transaction"]["1"], b.vertices["Transaction"]["2"]
    assert t1["card_id"] == "C09999-K1" and t1["addr1"] == "444" and t1["addr2"] == "87" and t1["device_profile"] == ""
    assert t2["addr1"] == "" and t2["device_status"] == "New" and t2["proxy_flag"] == "IP_PROXY:ANONYMOUS"
    assert set(b.vertices["DeviceProfile"]) == {"SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080"}
    assert set(b.vertices["EmailDomain"]) == {"gmail.com", "anonymous.com"}
    assert set(b.vertices["BillingRegion"]) == {"444"}
    kinds = sorted(e[2] for e in b.edges)
    assert kinds == ["BILLED_IN", "HAS_DEVICE", "RECIPIENT_EMAIL", "TRANS_ON_CARD", "TRANS_ON_CARD", "USES_EMAIL"]
    schema = gp.parse_schema(SCHEMA_TEXT)
    for vtype, rows in b.vertices.items():
        for attrs in rows.values():
            assert set(attrs) <= set(schema.vertices[vtype].attributes), vtype
    for e in b.edges:
        assert e[2] in schema.edges


def test_closed_cases_batch_only_links_existing_ids():
    closed = pd.DataFrame([{
        "case_id": "CC-0001", "customer_id": "C00259", "card_id": "C00259-K1", "opened_at": "2016-07-02 07:17:26",
        "closed_at": "2016-07-04 02:10:20", "outcome": "confirmed_fraud", "pattern": "card_testing",
        "first_fraud_txn_id": "3000001", "txn_ids": "3000001|3000002|9999999", "n_txns": "3", "exposure_usd": "12.5",
        "connected_card_ids": "C00877-K1|C99999-K9", "actions_taken": "CREATE_CASE|BLOCK_CARD", "report_filed": "Yes",
        "analyst_notes": "n",
    }])
    b = sg.closed_cases_to_batch(closed, {"3000001", "3000002"}, {"C00259-K1", "C00877-K1"})
    v = b.vertices["ClosedCase"]["CC-0001"]
    assert v["report_filed"] is True and v["exposure_usd"] == 12.5 and v["n_txns"] == 3
    kinds = sorted((e[2], e[4]) for e in b.edges)
    assert kinds == [("CASE_CONNECTED_CARD", "C00877-K1"), ("CASE_INCLUDES_TXN", "3000001"),
                     ("CASE_INCLUDES_TXN", "3000002"), ("PRIOR_CASE_ON", "C00259-K1")]


def test_dry_run_sink_and_split_batches_keep_every_row():
    cm = build_card_map([(f"C{i:05d}", "debit") for i in range(50)] + [("C00001", None)])
    sink = sg.DryRunSink()
    sg.push(sink, sg.cards_to_batch(cm), max_vertices=7)
    c = sink.counts()
    assert c["Customer"] == 50 and c["Card"] == 51 and c["OWNS_CARD"] == 51
    chunk = pd.DataFrame({
        "TransactionID": range(20), "TransactionDT": range(20), "TransactionAmt": [1.0] * 20, "ProductCD": ["C"] * 20,
        "card6": ["debit"] * 20, "addr1": [1.0] * 20, "addr2": [87.0] * 20, "P_emaildomain": ["a.com"] * 20,
        "R_emaildomain": [None] * 20, "customer_id": ["C00002"] * 20, "ts": ["2016-07-02 00:00:00"] * 20,
        "channel": ["online"] * 20, "risk_score": [0.1] * 20,
    })
    n = sg.push(sink, sg.transactions_to_batch(chunk, cm, {}), max_vertices=6)
    assert n == 4
    c = sink.counts()
    assert c["Transaction"] == 20 and c["TRANS_ON_CARD"] == 20 and c["BILLED_IN"] == 20 and c["USES_EMAIL"] == 20
    assert "HAS_DEVICE" not in c and "RECIPIENT_EMAIL" not in c


def test_restpp_params_wrap_typed_vertex_parameters():
    clean = fr.validate_params("card_window", {**GOOD, "max_rows": 5})
    body = fr.restpp_params("card_window", clean)
    assert body["card"] == {"id": "C00377-K1", "type": "Card"}
    assert body["window_start"] == GOOD["window_start"] and body["max_rows"] == 5
    w = fr.restpp_params("get_case_with_evidence", {"graph_case_id": "G"})
    assert w == {"graph_case_id": "G"}
