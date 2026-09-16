# tests/test_minimal_trader.py
"""
Minimal test - directly verify that the trader can receive and process events
No dependency on other components
"""
import asyncio
import time
import sys
from pathlib import Path

# Add project root directory
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Event
from app.main import load_cfg

# Import improved trader
import importlib.util
spec = importlib.util.spec_from_file_location(
    "trader_improved",
    ROOT / "tests" / "trader_improved.py"
)
trader_improved = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trader_improved)


async def main():
    print("\n" + "="*70)
    print("Minimal Trader Test")
    print("="*70)
    
    # 1. Load config
    print("\n[1] Loading config...")
    cfg = load_cfg()
    
    # Force-enable trader
    if 'trader' not in cfg:
        cfg['trader'] = {}
    
    cfg['trader']['enable'] = True
    cfg['trader']['dry_run'] = True
    cfg['trader']['buy_threshold'] = 80  # Lower threshold for easier testing
    cfg['trader']['max_position_per_symbol'] = 100
    
    # Ensure IBKR config exists
    if 'ibkr' not in cfg['trader']:
        cfg['trader']['ibkr'] = {
            'host': '127.0.0.1',
            'port': 7497,
            'client_id': 1
        }
    
    print("✓ Config loaded")
    print(f"  trader.enable = {cfg['trader']['enable']}")
    print(f"  trader.dry_run = {cfg['trader']['dry_run']}")
    print(f"  trader.buy_threshold = {cfg['trader']['buy_threshold']}")
    
    # 2. Create queue
    print("\n[2] Creating queue...")
    q_trade = asyncio.Queue()
    print("✓ Queue created")
    
    # 3. Start trader
    print("\n[3] Starting Trader...")
    trader_task = asyncio.create_task(
        trader_improved.run_trader_loop_improved(q_trade, cfg)
    )
    
    # Wait for trader to fully start
    await asyncio.sleep(3)
    
    # 4. Send test events
    print("\n[4] Sending test events...")
    
    now = int(time.time() * 1000)
    
    test_events = [
        Event(
            id="minimal_test_1",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="NVIDIA announces breakthrough AI chip with 10x performance gains",
            source="minimal_test",
            link="https://example.com/nvda",
            market="us",
            symbols="NVDA",
            categories="stock",
            tags="#ai #tech",
            score=95.0,  # High-score event
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="MIN_TEST_1",
        ),
        Event(
            id="minimal_test_2",
            ts_detected_utc=now + 1000,
            ts_published_utc=now + 1000,
            headline="Tesla reports record Q4 deliveries and strong margins",
            source="minimal_test",
            link="https://example.com/tsla",
            market="us",
            symbols="TSLA",
            categories="stock",
            tags="#ev",
            score=88.0,
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key="MIN_TEST_2",
        ),
    ]
    
    for i, ev in enumerate(test_events, 1):
        print(f"\n>>> Sending test event {i}/{len(test_events)}")
        print(f"    ID: {ev.id}")
        print(f"    Headline: {ev.headline}")
        print(f"    Score: {ev.score}")
        print(f"    Symbol: {ev.symbols}")
        
        await q_trade.put(ev)
        print(f"✓ Event enqueued (queue size: {q_trade.qsize()})")
        
        # Give trader time to process
        await asyncio.sleep(8)
    
    # 5. Wait for processing to complete
    print(f"\n[5] Waiting for all events to be processed...")
    print(f"    Current queue size: {q_trade.qsize()}")
    
    # Wait for queue to drain
    timeout = 30
    start = time.time()
    while q_trade.qsize() > 0 and (time.time() - start) < timeout:
        print(f"    Remaining in queue: {q_trade.qsize()}, waiting...")
        await asyncio.sleep(2)
    
    if q_trade.qsize() == 0:
        print("✓ All events processed")
    else:
        print(f"⚠️  Timeout: {q_trade.qsize()} event(s) still unprocessed")
    
    # 6. Cleanup
    print("\n[6] Cleaning up...")
    trader_task.cancel()
    try:
        await trader_task
    except asyncio.CancelledError:
        print("✓ Trader stopped")
    
    print("\n" + "="*70)
    print("Test complete")
    print("="*70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()