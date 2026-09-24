"""Card-ID derivation (graph/card_id.py): unit tests on synthetic frames + validation against
the real labels when the (uncommitted) transactions.csv is present locally."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from graph import card_id as ci
from graph.setup_graph import CASE_PACK_CSV, CLOSED_CASES_CSV, TRANSACTIONS_CSV

# ------------------------------------------------------------------ unit: the rule itself


def test_normalise_card6_blank_variants():
    for v in (None, float("nan"), "", " ", "nan", "NaN", "<NA>", pd.NA):
        assert ci.normalise_card6(v) == ""
    assert ci.normalise_card6(" debit ") == "debit"
    assert ci.normalise_card6("credit") == "credit"


def test_blank_sorts_first_then_ascending():
    cm = ci.build_card_map([("C00001", "debit"), ("C00001", None), ("C00001", "credit")])
    assert cm.by_customer["C00001"] == {"": "C00001-K1", "credit": "C00001-K2", "debit": "C00001-K3"}


def test_single_card_customer_is_k1_and_duplicates_ignored():
    cm = ci.build_card_map([("C00002", "debit")] * 5)
    assert cm.by_customer["C00002"] == {"debit": "C00002-K1"}
    assert cm.n_cards == 1 and cm.n_customers == 1


def test_card4_and_other_columns_do_not_split_cards():
    # Same customer, same card6, different card4/card2/card5 -> ONE card (validated on labels).
    df = pd.DataFrame(
        {
            "TransactionID": [1, 2, 3],
            "customer_id": ["C00003"] * 3,
            "card6": ["credit", "credit", "credit"],
            "card4": ["visa", "mastercard", None],
            "card2": [111.0, 222.0, float("nan")],
            "card5": [102.0, 137.0, 226.0],
        }
    )
    cm = ci.build_card_map_from_frame(df)
    assert cm.n_cards == 1
    assert list(ci.assign_card_ids(df, cm)) == ["C00003-K1"] * 3


def test_assign_card_ids_and_lookup_are_consistent():
    df = pd.DataFrame(
        {
            "TransactionID": [10, 11, 12, 13],
            "customer_id": ["C1", "C1", "C2", "C1"],
            "card6": ["debit", "credit", None, "debit"],
        }
    )
    cm = ci.build_card_map_from_frame(df)
    got = list(ci.assign_card_ids(df, cm))
    assert got == ["C1-K2", "C1-K1", "C2-K1", "C1-K2"]
    assert cm.card_id_for("C1", "debit") == "C1-K2"
    with pytest.raises(KeyError):
        cm.card_id_for("C1", "charge card")
    rows = sorted(cm.rows())
    assert rows == [("C1-K1", "C1", "credit", 1), ("C1-K2", "C1", "debit", 2), ("C2-K1", "C2", "", 1)]
    assert cm.cards_per_customer_histogram() == {1: 1, 2: 1}
    assert cm.all_card_ids() == {"C1-K1", "C1-K2", "C2-K1"}


def test_validation_report_material_flag():
    rep = ci.ValidationReport(closed_txns_total=10, closed_txns_matched=10, case_pack_total=2, case_pack_matched=2)
    assert not rep.material and rep.closed_txn_mismatch_rate == 0
    rep.closed_txns_matched = 9
    assert rep.material and math.isclose(rep.closed_txn_mismatch_rate, 0.1)


def test_validate_against_labels_on_tmp_files(tmp_path):
    closed = tmp_path / "closed.csv"
    closed.write_text(
        "case_id,customer_id,card_id,txn_ids,connected_card_ids\n"
        "CC-1,C1,C1-K2,10|13,C2-K1\n"
        "CC-2,C1,C1-K1,11,\n"
        "CC-3,C9,C9-K1,99,\n",
        encoding="utf-8",
    )
    pack = tmp_path / "pack.csv"
    pack.write_text("case_id,flagged_txn_id,card_id\nHHG-001,12,C2-K1\nHHG-002,10,C1-K1\n", encoding="utf-8")
    txn_card = {"10": "C1-K2", "11": "C1-K1", "12": "C2-K1", "13": "C1-K2"}
    cm = ci.build_card_map([("C1", "credit"), ("C1", "debit"), ("C2", None)])
    rep = ci.validate_against_labels(txn_card, cm, closed, pack)
    assert rep.closed_txns_total == 4 and rep.closed_txns_matched == 3 and rep.closed_txns_missing == 1
    assert rep.closed_cases_fully_matched == 2
    assert rep.case_pack_total == 2 and rep.case_pack_matched == 1
    assert rep.connected_card_ids_total == 1 and rep.connected_card_ids_existing == 1
    assert rep.material
    assert rep.mismatches[0]["case_id"] == "HHG-002"


def test_only_needed_columns_are_read(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("TransactionID,card1,card6,V1,customer_id\n1,9,debit,0.5,C1\n2,9,,0.1,C1\n", encoding="utf-8")
    chunks = list(ci.iter_transaction_chunks(p, ci.COLUMNS, chunk_rows=1))
    assert len(chunks) == 2
    assert set(chunks[0].columns) == set(ci.COLUMNS)  # V1 and card1 never loaded
    cm = ci.build_card_map_from_csv(p, chunk_rows=1)
    assert cm.by_customer == {"C1": {"": "C1-K1", "debit": "C1-K2"}}


# ------------------------------------------------------------------ real labels (local data)

needs_data = pytest.mark.skipif(not TRANSACTIONS_CSV.exists(), reason="transactions.csv is not committed; run locally")


@pytest.fixture(scope="module")
def real_derivation():
    cm = ci.build_card_map_from_csv(TRANSACTIONS_CSV)
    txn_card = ci.derive_txn_card_ids(TRANSACTIONS_CSV, cm)
    rep = ci.validate_against_labels(txn_card, cm, CLOSED_CASES_CSV, CASE_PACK_CSV)
    return cm, txn_card, rep


@needs_data
@pytest.mark.data
def test_real_derivation_matches_every_label(real_derivation):
    cm, txn_card, rep = real_derivation
    assert not rep.material, rep.as_dict()
    assert rep.closed_txns_total == 14_955 and rep.closed_txns_matched == 14_955
    assert rep.closed_cases_total == 5_565 and rep.closed_cases_fully_matched == 5_565
    assert rep.case_pack_total == 20 and rep.case_pack_matched == 20
    assert rep.connected_card_ids_total == rep.connected_card_ids_existing > 0


@needs_data
@pytest.mark.data
def test_real_derivation_shape(real_derivation):
    cm, txn_card, _ = real_derivation
    assert cm.n_customers == 13_553
    assert cm.n_cards == 14_317
    assert cm.cards_per_customer_histogram() == {1: 12_793, 2: 756, 3: 4}
    assert len(txn_card) == 590_742
    assert all(c.startswith("C") and "-K" in c for c in cm.all_card_ids())
