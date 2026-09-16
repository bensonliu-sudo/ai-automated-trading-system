# tests/test_trader_llm_only.py

import asyncio
import time
import pathlib
import yaml

from app.main import run_trader_loop
from app.models import Event


async def main():
    # 1. Read config (consistent with test_full_pipeline)
    ROOT = pathlib.Path(__file__).resolve().parents[1]
    cfg_path = ROOT / "ops" / "config.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # 2. Only q_scored is needed; one queue is enough
    q_scored: asyncio.Queue = asyncio.Queue()

    # 3. Start trader (initializes LLM and IBKR, but dry_run=True places no real orders)
    trader_task = asyncio.create_task(run_trader_loop(q_scored, cfg))

    # 4. Build a few test Events and push them straight into q_scored

    now = int(time.time() * 1000)

    events = [
        Event(
            id="test_nvda_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="NVIDIA releases new AI GPU H200 with massive performance gains",
            source="unit_test",
            link="https://example.com/nvda",
            market="us",
            symbols="NVDA",          # A single ticker is written as a plain string
            categories="stock",
            tags="#ai",
            score=90.0,              # Above buy_threshold
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="TEST_NVDA",
        ),
        Event(
            id="test_tsla_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="TSLA announces record EV deliveries this quarter",
            source="unit_test",
            link="https://example.com/tsla",
            market="us",
            symbols="TSLA",
            categories="stock",
            tags="#ev",
            score=80.0,
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="TEST_TSLA",
        ),
        Event(
            id="test_sector_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="US Semiconductor sector surges on strong data center demand",
            source="unit_test",
            link="https://example.com/sector",
            market="us",
            symbols="",             # Deliberately omit the ticker so the LLM decides on its own
            categories="sector",
            tags="#semi",
            score=85.0,
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="TEST_SECTOR",
        ),
    ]

    for ev in events:
        print(f"[test] PUT to q_scored: {ev.id} | {ev.headline} | score={ev.score}")
        await q_scored.put(ev)
        # Give trader a little time to process each one
        await asyncio.sleep(2)

    # Wait a bit longer and check the logs
    await asyncio.sleep(20)

    # 5. Stop trader
    trader_task.cancel()
    try:
        await trader_task
        
    except asyncio.CancelledError:
        pass

    print("[test] trader llm only test finished.")


if __name__ == "__main__":
    asyncio.run(main())