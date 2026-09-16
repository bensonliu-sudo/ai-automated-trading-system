# -*- coding: utf-8 -*-
"""
tests/test_storage.py
Verify that app/storage.py integrates correctly with the Event model:
1) init_db -> insert_event
2) get_recent_events can retrieve the just-inserted row
"""
# === Ensure app can be imported correctly ===
import sys,os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.collector import run_collectors
from app.scorer import run_scorer
from app.storage import init_db
import asyncio
import time
from pathlib import Path

from app.storage import init_db, insert_event, get_recent_events
# Try to import Event; if construction fails, this test falls back to a dict
try:
    from app.models import Event  # The Event from your project
except Exception:  # noqa
    Event = None


def now_ms() -> int:
    return int(time.time() * 1000)


async def main():
    root = Path(__file__).resolve().parents[1]
    db_path = root / "intel.db"
    db = await init_db(db_path)

    # Unique ID to avoid collisions
    uid = f"test_storage_{int(time.time())}"

    # Common event fields
    ts = now_ms()
    payload = dict(
        id=uid,
        ts_detected_utc=ts,
        ts_published_utc=ts,
        headline="(TEST) Broadcom and Canonical expand partnership to optimize VMware Cloud Foundation",
        source="broadcom_news",
        link="https://example.com/test",
        market="us",
        symbols="AVGO",
        categories="partnership;cloud",
        tags="#AI;#Semis",
        score=80.0,
        pushed=0,
        expires_at_utc=ts + 24 * 3600 * 1000,
        thread_key="AVGO|partnership",
        raw={"test": True},
    )

    # Prefer constructing an Event; fall back to dict on failure
    ev_obj = None
    if Event is not None:
        try:
            ev_obj = Event(**payload)  # Raises if your Event interface differs
        except Exception:
            ev_obj = None

    to_write = ev_obj if ev_obj is not None else payload

    # Write (idempotent upsert)
    ok = await insert_event(db, to_write)
    if not ok:
        raise SystemExit("❌ insert_event returned False")

    # Query
    rows = await get_recent_events(db, since_ms=ts - 60_000, min_score=0, limit=200)
    ids = [r["id"] for r in rows]
    if uid not in ids:
        # Print a debug line to help locate the issue
        print("rows sample (top 3):", rows[:3])
        raise SystemExit("❌ Query result does not contain the just-inserted event")

    print("OK ✅")


if __name__ == "__main__":
    asyncio.run(main())