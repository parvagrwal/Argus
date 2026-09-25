"""Record vector_similar_cases query results for benchmark and bonus cases into offline fixtures."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any

from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.loop import CaseInput
from mcp.fallback_rest import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("argus.record_vector_fixtures")

CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
BONUS_DIR = ROOT / "bonus_cases"
FIXTURES_DIR = ROOT / "fixtures"


def load_all_cases() -> list[CaseInput]:
    cases: list[CaseInput] = []
    if CASE_PACK_CSV.exists():
        with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cases.append(CaseInput(
                    r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                    r["flagged_txn_id"], r["card_id"], r["customer_id"],
                    float(r["risk_score"]) if r["risk_score"] else None,
                ))

    manifest_path = BONUS_DIR / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for r in data:
            cases.append(CaseInput(
                r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                r["flagged_txn_id"], r["card_id"], r["customer_id"],
                float(r["risk_score"]) if r["risk_score"] else None,
            ))
    return cases


def record_vector_fixtures() -> None:
    client = get_client()
    cases = load_all_cases()
    log.info(f"Loading embedding model for {len(cases)} cases...")
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    for case in cases:
        query_text = f"{case.trigger_type}: {case.trigger_text}"
        q_vec = model.encode(query_text, normalize_embeddings=True).tolist()
        res = client.run_query("vector_similar_cases", query_vector=q_vec, k=3)

        case_dir = FIXTURES_DIR / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = case_dir / "vector_similar_cases.json"

        data = {
            "fixture": True,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "live TigerGraph SENTINEL (vectorSearch)",
            "query": "vector_similar_cases",
            "params": {"query_text": query_text, "k": 3},
            "response": res,
        }
        fixture_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        raw_items = res.get("results", [{}])[0].get("similar_cases", [])
        cids = [it.get("v_id") or it.get("attributes", {}).get("Res.case_id") for it in raw_items]
        log.info(f"Recorded vector fixture for {case.case_id}: {cids}")

    log.info(f"Successfully recorded all vector fixtures to {FIXTURES_DIR}")


if __name__ == "__main__":
    record_vector_fixtures()
