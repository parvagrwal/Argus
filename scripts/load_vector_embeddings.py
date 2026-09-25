"""Load and upsert note_text and note_embedding for all 5,565 closed cases."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.fallback_rest import TGConfig, GraphAdmin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("argus.vector_loader")


def main() -> None:
    csv_path = ROOT / "data" / "closed_cases_history.csv"
    if not csv_path.exists():
        log.error(f"Missing CSV: {csv_path}")
        sys.exit(1)

    log.info("Reading closed_cases_history.csv...")
    df = pd.read_csv(csv_path, dtype=str)
    n_cases = len(df)
    log.info(f"Loaded {n_cases} rows from CSV")

    log.info("Loading sentence-transformers all-MiniLM-L6-v2 on CPU...")
    t0 = time.time()
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    log.info(f"Model loaded in {time.time() - t0:.2f}s")

    notes = [str(r) if pd.notna(r) else "" for r in df["analyst_notes"]]
    log.info("Computing embeddings on CPU...")
    t0 = time.time()
    embeddings = model.encode(notes, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
    log.info(f"Computed {len(embeddings)} embeddings (dim {len(embeddings[0])}) in {time.time() - t0:.2f}s")

    cfg = TGConfig.from_env()
    admin = GraphAdmin(cfg)
    tok = admin._get_token()
    if not tok:
        log.error("Failed to obtain TigerGraph auth token")
        sys.exit(1)

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}
    url = f"{cfg.restpp}/graph/{cfg.graph}"

    batch_size = 500
    total_accepted = 0
    t0 = time.time()

    for i in range(0, n_cases, batch_size):
        chunk_df = df.iloc[i : i + batch_size]
        chunk_embs = embeddings[i : i + batch_size]

        v_dict = {}
        for row, emb in zip(chunk_df.itertuples(), chunk_embs):
            cid = row.case_id
            note_raw = getattr(row, "analyst_notes", "") or ""
            note_500 = str(note_raw)[:500]
            v_dict[cid] = {
                "note_text": {"value": note_500},
                "note_embedding": {"value": [round(float(x), 6) for x in emb]},
            }

        payload = {"vertices": {"ClosedCase": v_dict}}
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        if not resp.ok:
            log.error(f"Batch {i} failed: {resp.status_code} {resp.text[:300]}")
            sys.exit(1)

        res_json = resp.json()
        accepted = res_json.get("results", [{}])[0].get("accepted_vertices", 0)
        total_accepted += accepted
        log.info(f"Upserted batch {i}..{i + len(chunk_df)}: accepted={accepted} (total={total_accepted}/{n_cases})")

    log.info(f"Upsert complete! Total accepted: {total_accepted} in {time.time() - t0:.2f}s")

    # Spot-check 3 vertices
    spot_checks = ["CC-0001", "CC-2500", "CC-5565"]
    log.info("Spot checking 3 vertices:")
    for cid in spot_checks:
        r = requests.get(f"{cfg.restpp}/graph/{cfg.graph}/vertices/ClosedCase/{cid}", headers={"Authorization": f"Bearer {tok}"})
        if r.ok:
            data = r.json()
            attrs = data.get("results", [{}])[0].get("attributes", {})
            log.info(f"  [{cid}] outcome={attrs.get('outcome')}, note_text[:80]={attrs.get('note_text', '')[:80]!r}")
        else:
            log.warning(f"  [{cid}] fetch failed: {r.status_code}")


if __name__ == "__main__":
    main()
