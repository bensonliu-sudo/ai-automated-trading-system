# tests/test_full_pipeline.py
import asyncio
import time
import pathlib
import yaml

# ✅ Import everything from main
from app.main import init_db, run_scorer, run_trader_loop


async def main():
    # 1. Prepare paths & load config
    ROOT = pathlib.Path(__file__).resolve().parents[1]

    cfg_path = ROOT / "ops" / "config.yml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    print("[scorer] Config loaded")

    # 2. Initialize database (consistent with main.py)
    db_path = ROOT / "intel.db"
    db = await init_db(db_path)
    print(f"[test] db at {db_path}")

    # 3. Prepare queues
    q_raw = asyncio.Queue()
    q_scored = asyncio.Queue()

    # 4. Start scorer + trader
    print("[test] starting scorer & trader...")
    tasks = [
        asyncio.create_task(run_scorer(q_raw, q_scored, db)),
        asyncio.create_task(run_trader_loop(q_scored, cfg)),
    ]

    # 5. Build a "raw news" item and push it into q_raw
    #    Note: a dict is used here instead of an Event instance; scorer already supports both
    now = int(time.time() * 1000)

    raw_event = {
        "id": "test_event_1",
        "ts_detected_utc": now,
        "ts_published_utc": now,
        "headline": "NVIDIA releases new AI GPU H200 with massive performance gains",
        "body": "The new GPU is expected to drive strong demand among datacenter clients.",
        "source": "unit_test",
        "link": "https://example.com",
        "market": "us",
        "symbols": ["NVDA"],
        "categories": ["stock"],
        "tags": "#ai",
        # This score will be recomputed by scorer, but set a value > buy_threshold for easier debugging
        "score": 85,
        "pushed": 0,
        "expires_at_utc": now + 3600_000,
        "thread_key": "TEST",
    }

    print("[test] sending test raw_event to q_raw...")
    await q_raw.put(raw_event)

    # 6. Let it run for a while (scorer -> LLM -> trader have time to process)
    #    Normally you should see:
    #      - scorer prints the score
    #      - LLM raw response / LLM decision
    #      - [IBKR] BUY NVDA x 100 (dry_run=True, no real order is placed)
    await asyncio.sleep(10)

    # 7. Finish tasks
    print("[test] cancelling tasks...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    print("[test] full pipeline test finished.")


if __name__ == "__main__":
    asyncio.run(main())