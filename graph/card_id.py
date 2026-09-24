"""
Deterministic card-ID derivation — P1.

`transactions.csv` has no `card_id` column (data/INVENTORY.md, D-15). Case files use IDs of
the form `C01234-K2`. This module reproduces them from real columns only.

Rule (validated 2026-09-24 against every closed case and the case pack — see
data/GRAPH_SCHEMA.md §3 for the study and the alternatives that were rejected):

    card_id = f"{customer_id}-K{k}"
    where k = 1-based rank of the transaction's `card6` value among the distinct `card6`
    values of that customer, sorted ascending with a blank (missing) value first.

Facts the rule rests on (all measured on the real data):
  * `card1` is one-to-one with `customer_id` (13,553 each), so it identifies the customer,
    not the card.
  * `card3`, `card4`, `card6` never vary inside a labelled card; `card2` and `card5` do
    (25 and 19 of 1,913 labelled cards), so they cannot be part of the key.
  * `card6` alone reproduces 14,955 / 14,955 labelled closed-case transactions
    (5,565 / 5,565 cases) and 20 / 20 case-pack cards. `card4`+`card6` also scores 100 %
    on the labels but splits exactly one extra customer (C11039, not in any case) whose
    `card4` is blank on one row; we treat that as missing data, not a second card.
  * Sort order is the observed label order: blank < "charge card" < "credit" < "debit"
    < "debit or credit" (plain ascending string sort with "" first).

Nothing here touches an LLM or the network. Only the columns named in COLUMNS are read.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

CARD_KEY_COLUMNS: tuple[str, ...] = ("card6",)  # the key that survived validation
COLUMNS: tuple[str, ...] = ("TransactionID", "customer_id") + CARD_KEY_COLUMNS
DEFAULT_CHUNK_ROWS = 100_000

_TEXT_COLUMNS = {
    "customer_id", "card6", "card4", "ProductCD", "ts", "channel",
    "P_emaildomain", "R_emaildomain",
}


def normalise_card6(value: object) -> str:
    """Blank/NaN -> "" so that missing sorts first; everything else a stripped string."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if value is pd.NA:
        return ""
    s = str(value).strip()
    if s.lower() in {"", "nan", "<na>", "none"}:
        return ""
    return s


@dataclass(frozen=True)
class CardMap:
    """customer_id -> {card6_value -> card_id}; built once, applied to any row stream."""

    by_customer: dict[str, dict[str, str]]

    def card_id_for(self, customer_id: str, card6: object) -> str:
        key = normalise_card6(card6)
        try:
            return self.by_customer[str(customer_id)][key]
        except KeyError as exc:
            raise KeyError(f"no card for customer={customer_id!r} card6={key!r}") from exc

    @property
    def n_cards(self) -> int:
        return sum(len(v) for v in self.by_customer.values())

    @property
    def n_customers(self) -> int:
        return len(self.by_customer)

    def cards_per_customer_histogram(self) -> dict[int, int]:
        hist: dict[int, int] = {}
        for v in self.by_customer.values():
            hist[len(v)] = hist.get(len(v), 0) + 1
        return dict(sorted(hist.items()))

    def rows(self) -> Iterator[tuple[str, str, str, int]]:
        """(card_id, customer_id, card6, k_index) for every derived card."""
        for cust, m in self.by_customer.items():
            for card6, cid in m.items():
                yield cid, cust, card6, int(cid.rsplit("-K", 1)[1])

    def all_card_ids(self) -> set[str]:
        return {cid for cid, *_ in self.rows()}

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(list(self.rows()), columns=["card_id", "customer_id", "card6", "k_index"])


def build_card_map(pairs: Iterable[tuple[str, object]]) -> CardMap:
    """Build the map from an iterable of (customer_id, card6) pairs (duplicates are fine)."""
    seen: dict[str, set[str]] = {}
    for customer_id, card6 in pairs:
        seen.setdefault(str(customer_id), set()).add(normalise_card6(card6))
    by_customer = {
        cust: {card6: f"{cust}-K{i}" for i, card6 in enumerate(sorted(values), start=1)}
        for cust, values in seen.items()
    }
    return CardMap(by_customer=by_customer)


def build_card_map_from_frame(df: pd.DataFrame) -> CardMap:
    sub = df[["customer_id", "card6"]]
    return build_card_map(zip(sub["customer_id"].astype(str), sub["card6"]))


def iter_transaction_chunks(
    path: str | Path, columns: Iterable[str], chunk_rows: int = DEFAULT_CHUNK_ROWS
) -> Iterator[pd.DataFrame]:
    """Chunk-read `transactions.csv` with an explicit column selection. Never the full width."""
    cols = list(columns)
    dtype = {c: "string" for c in cols if c in _TEXT_COLUMNS}
    for chunk in pd.read_csv(path, usecols=cols, chunksize=chunk_rows, dtype=dtype or None):
        yield chunk


def build_card_map_from_csv(path: str | Path, chunk_rows: int = DEFAULT_CHUNK_ROWS) -> CardMap:
    """First pass over transactions.csv reading only customer_id + card6."""
    pairs: set[tuple[str, str]] = set()
    for chunk in iter_transaction_chunks(path, ("customer_id",) + CARD_KEY_COLUMNS, chunk_rows):
        uniq = chunk[["customer_id", "card6"]].drop_duplicates()
        pairs.update((str(c), normalise_card6(k)) for c, k in zip(uniq["customer_id"], uniq["card6"]))
    return build_card_map(pairs)


def assign_card_ids(chunk: pd.DataFrame, card_map: CardMap) -> pd.Series:
    """Vectorised card_id column for a chunk that has customer_id and card6."""
    keys = chunk["card6"].map(normalise_card6)
    values = [card_map.by_customer[str(c)][k] for c, k in zip(chunk["customer_id"], keys)]
    return pd.Series(values, index=chunk.index, dtype="string")


# --------------------------------------------------------------------------------------
# Validation against the labelled files (closed_cases_history.csv, case_pack.csv)
# --------------------------------------------------------------------------------------


@dataclass
class ValidationReport:
    closed_txns_total: int = 0
    closed_txns_matched: int = 0
    closed_txns_missing: int = 0  # txn ids not found in transactions.csv
    closed_cases_total: int = 0
    closed_cases_fully_matched: int = 0
    case_pack_total: int = 0
    case_pack_matched: int = 0
    connected_card_ids_total: int = 0
    connected_card_ids_existing: int = 0
    mismatches: list[dict[str, str]] = field(default_factory=list)  # first 50 only

    @property
    def closed_txn_mismatch_rate(self) -> float:
        if not self.closed_txns_total:
            return 0.0
        return 1 - self.closed_txns_matched / self.closed_txns_total

    @property
    def case_pack_mismatch_rate(self) -> float:
        if not self.case_pack_total:
            return 0.0
        return 1 - self.case_pack_matched / self.case_pack_total

    @property
    def material(self) -> bool:
        """Any mismatch at all is material: the labels are exact IDs, not estimates."""
        return (
            self.closed_txns_matched != self.closed_txns_total
            or self.case_pack_matched != self.case_pack_total
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "closed_txns_total": self.closed_txns_total,
            "closed_txns_matched": self.closed_txns_matched,
            "closed_txns_missing_from_transactions": self.closed_txns_missing,
            "closed_txn_mismatch_rate": round(self.closed_txn_mismatch_rate, 6),
            "closed_cases_total": self.closed_cases_total,
            "closed_cases_fully_matched": self.closed_cases_fully_matched,
            "case_pack_total": self.case_pack_total,
            "case_pack_matched": self.case_pack_matched,
            "case_pack_mismatch_rate": round(self.case_pack_mismatch_rate, 6),
            "connected_card_ids_total": self.connected_card_ids_total,
            "connected_card_ids_existing": self.connected_card_ids_existing,
            "material": self.material,
            "mismatch_examples": self.mismatches[:10],
        }


def derive_txn_card_ids(
    transactions_csv: str | Path, card_map: CardMap, chunk_rows: int = DEFAULT_CHUNK_ROWS
) -> dict[str, str]:
    """Second pass: TransactionID -> card_id for every transaction (~590k short strings)."""
    out: dict[str, str] = {}
    for chunk in iter_transaction_chunks(transactions_csv, COLUMNS, chunk_rows):
        ids = assign_card_ids(chunk, card_map)
        out.update(zip(chunk["TransactionID"].astype(str), ids))
    return out


def validate_against_labels(
    txn_card: dict[str, str],
    card_map: CardMap,
    closed_cases_csv: str | Path,
    case_pack_csv: str | Path,
) -> ValidationReport:
    rep = ValidationReport()
    all_cards = card_map.all_card_ids()

    with open(closed_cases_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rep.closed_cases_total += 1
            ok_case = True
            for tid in filter(None, (row["txn_ids"] or "").split("|")):
                rep.closed_txns_total += 1
                derived = txn_card.get(tid)
                if derived is None:
                    rep.closed_txns_missing += 1
                    ok_case = False
                    continue
                if derived == row["card_id"]:
                    rep.closed_txns_matched += 1
                else:
                    ok_case = False
                    if len(rep.mismatches) < 50:
                        rep.mismatches.append(
                            {"case_id": row["case_id"], "txn_id": tid, "label": row["card_id"], "derived": derived}
                        )
            if ok_case:
                rep.closed_cases_fully_matched += 1
            for cc in filter(None, (row.get("connected_card_ids") or "").split("|")):
                rep.connected_card_ids_total += 1
                rep.connected_card_ids_existing += int(cc in all_cards)

    with open(case_pack_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rep.case_pack_total += 1
            derived = txn_card.get(row["flagged_txn_id"])
            if derived == row["card_id"]:
                rep.case_pack_matched += 1
            elif len(rep.mismatches) < 50:
                rep.mismatches.append(
                    {
                        "case_id": row["case_id"],
                        "txn_id": row["flagged_txn_id"],
                        "label": row["card_id"],
                        "derived": derived or "<missing>",
                    }
                )
    return rep


if __name__ == "__main__":  # manual check: python -m graph.card_id
    import json
    import sys

    root = Path(__file__).resolve().parents[1] / "data"
    cm = build_card_map_from_csv(root / "transactions.csv")
    tc = derive_txn_card_ids(root / "transactions.csv", cm)
    rep = validate_against_labels(tc, cm, root / "closed_cases_history.csv", root / "case_pack.csv")
    print(
        json.dumps(
            {
                "cards": cm.n_cards,
                "customers": cm.n_customers,
                "cards_per_customer": cm.cards_per_customer_histogram(),
                **rep.as_dict(),
            },
            indent=2,
        )
    )
    sys.exit(1 if rep.material else 0)
