"""Record live TigerGraph queries into offline fixtures.

Runs all 5 read queries for the 20 benchmark cases and all bonus cases against live TigerGraph,
saving raw responses to fixtures/<case_id>/<query>.json. Does NOT perform write_back.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import scoring as S
from agent.loop import CaseInput
from mcp.fallback_rest import get_client

CASE_PACK_CSV = ROOT / "data" / "case_pack.csv"
BONUS_DIR = ROOT / "bonus_cases"
FIXTURES_DIR = ROOT / "fixtures"


def load_all_cases() -> list[CaseInput]:
    cases: list[CaseInput] = []
    # 20 benchmark cases
    if CASE_PACK_CSV.exists():
        with open(CASE_PACK_CSV, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                cases.append(CaseInput(
                    r["case_id"], r["opened_at"], r["trigger_type"], r["trigger_text"],
                    r["flagged_txn_id"], r["card_id"], r["customer_id"],
                    float(r["risk_score"]) if r["risk_score"] else None,
                ))

    # Bonus cases
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


def record_fixtures() -> None:
    client = get_client()
    cases = load_all_cases()
    print(f"Recording fixtures for {len(cases)} cases (20 benchmark + {len(cases) - 20} bonus)...")

    for case in cases:
        case_dir = FIXTURES_DIR / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        end = case.opened_at
        start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        burst_start = (datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(hours=78)).strftime("%Y-%m-%d %H:%M:%S")

        # 1. card_window
        cw_params = {"card": case.card_id, "window_start": start, "window_end": end, "max_rows": 500}
        cw_res = client.run_query("card_window", **cw_params)
        _save_fixture(case.case_id, "card_window", cw_params, cw_res)

        f = S.Features()
        S.apply_card_window(f, cw_res, case.flagged_txn_id, end)
        flagged_region = str(f.flagged.get("addr1", "") or "")

        # 2. velocity_check
        vc_params = {"card": case.card_id, "window_start": burst_start, "window_end": end}
        vc_res = client.run_query("velocity_check", **vc_params)
        _save_fixture(case.case_id, "velocity_check", vc_params, vc_res)

        # 3. region_profile
        rp_params = {"card": case.card_id, "window_start": start, "window_end": end, "flagged_region": flagged_region}
        rp_res = client.run_query("region_profile", **rp_params)
        _save_fixture(case.case_id, "region_profile", rp_params, rp_res)

        # 4. device_neighbors
        dn_params = {"card": case.card_id, "window_start": start, "window_end": end}
        dn_res = client.run_query("device_neighbors", **dn_params)
        _save_fixture(case.case_id, "device_neighbors", dn_params, dn_res)

        # 5. detect_fraud_ring
        dfr_params = {"card": case.card_id, "window_start": start, "window_end": end}
        dfr_res = client.run_query("detect_fraud_ring", **dfr_params)
        _save_fixture(case.case_id, "detect_fraud_ring", dfr_params, dfr_res)

        print(f"Recorded 5 fixtures for {case.case_id} (card: {case.card_id})")

    print(f"Successfully recorded all fixtures to {FIXTURES_DIR}")


def _save_fixture(case_id: str, query: str, params: dict[str, Any], response: dict[str, Any]) -> None:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "fixture": True,
        "recorded_at": now_utc,
        "source": "live TigerGraph SENTINEL",
        "query": query,
        "params": params,
        "response": response,
    }
    path = FIXTURES_DIR / case_id / f"{query}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    record_fixtures()
