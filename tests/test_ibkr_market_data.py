import asyncio
import sys
from pathlib import Path

# Add project root directory to sys.path
ROOT = Path(__file__).resolve().parents[1]   # intel-hub/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.trader import IBKRTrader


async def main():
    # Load config (config.yml already exists)
    import yaml
    from pathlib import Path

    cfg_path = Path("ops/config.yml")
    cfg = yaml.safe_load(cfg_path.read_text())

    ibkr_cfg = cfg["trader"]["ibkr"]

    print("\n=== IBKR Connection Test ===")

    trader = IBKRTrader(ibkr_cfg, dry_run=True)   # dry_run=True can still fetch market data
    await trader.connect()

    symbols = ["NVDA", "AAPL", "MSFT", "TSLA"]

    print("\n=== Fetching Real-Time Quotes ===")
    for sym in symbols:
        try:
            price = await trader.get_last_price(sym)
            print(f"{sym}: {price}")
        except Exception as e:
            print(f"{sym}: fetch failed -> {e}")

    await trader.close()
    print("\n=== Test Finished ===")


if __name__ == "__main__":
    asyncio.run(main())