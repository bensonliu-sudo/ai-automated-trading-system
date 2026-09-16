# tests/debug_pipeline.py
"""
Debug issues in the full pipeline
"""
import asyncio
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Event
from app.main import fanout_scored, run_trader_loop, load_cfg


async def main():
    print("\n" + "="*70)
    print("Debug Full Pipeline")
    print("="*70)
    
    # 1. Load config
    cfg = load_cfg()
    
    print("\n[1] Config check:")
    print(f"  trader.enable = {cfg.get('trader', {}).get('enable')}")
    print(f"  trader.buy_threshold = {cfg.get('trader', {}).get('buy_threshold')}")
    
    # 2. Create queues (same structure as main.py)
    q_scored_master = asyncio.Queue()
    q_notify = asyncio.Queue()
    q_trade = asyncio.Queue()
    
    # 3. Start fanout and trader
    print("\n[2] Starting components...")
    
    fanout_task = asyncio.create_task(
        fanout_scored(q_scored_master, q_notify, q_trade)
    )
    
    trader_task = asyncio.create_task(
        run_trader_loop(q_trade, cfg)
    )
    
    # Mock notifier (print only)
    async def mock_notifier():
        while True:
            ev = await q_notify.get()
            print(f"[mock_notifier] received: {ev.id}, score={ev.score}")
            q_notify.task_done()
    
    notifier_task = asyncio.create_task(mock_notifier())
    
    await asyncio.sleep(2)
    
    # 4. Send test events to q_scored_master
    print("\n[3] Sending test events...")
    
    now = int(time.time() * 1000)
    
    test_events = [
        Event(
            id="debug_test_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="NVIDIA announces breakthrough H200 GPU with 10x performance",
            source="debug_test",
            link="https://example.com",
            market="us",
            symbols="NVDA",
            categories="stock",
            tags="#ai",
            score=95.0,  # High score
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="DEBUG_1",
        ),
        Event(
            id="debug_test_2",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="Low score event",
            source="debug_test",
            link="https://example.com",
            market="us",
            symbols="AAPL",
            categories="stock",
            tags="#test",
            score=30.0,  # Low score
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="DEBUG_2",
        ),
    ]
    
    for i, ev in enumerate(test_events, 1):
        print(f"\n>>> Sending event {i}: {ev.headline[:50]}... (score={ev.score})")
        await q_scored_master.put(ev)
        print(f"    Put into q_scored_master")
        
        # Wait a moment and observe the logs
        await asyncio.sleep(3)
    
    # 5. Check queue status
    print("\n[4] Queue status:")
    print(f"  q_scored_master: {q_scored_master.qsize()}")
    print(f"  q_notify: {q_notify.qsize()}")
    print(f"  q_trade: {q_trade.qsize()}")
    
    # Wait for processing
    print("\n[5] Waiting for processing...")
    await asyncio.sleep(10)
    
    # 6. Cleanup
    print("\n[6] Cleaning up...")
    for task in [fanout_task, trader_task, notifier_task]:
        task.cancel()
    
    await asyncio.gather(fanout_task, trader_task, notifier_task, return_exceptions=True)
    
    print("\n" + "="*70)
    print("Debug complete")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())