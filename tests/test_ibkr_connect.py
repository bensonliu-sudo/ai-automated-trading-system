# tests/test_ibkr_connect.py

import asyncio
from app.trader import IBKRTrader

IBKR_CFG = {
    "host": "127.0.0.1",
    "port": 7497,    # TWS paper trading default port
    "client_id": 1,
}


async def main():
    print("[test] trying to connect to IBKR TWS paper trading...")

    trader = IBKRTrader(IBKR_CFG, dry_run=True)

    try:
        await trader.connect()
        print("[test] SUCCESS: connected to IBKR!")
        print("[test] current positions:", trader.positions)
    except Exception as e:
        print("[test] FAILED:", repr(e))
    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(main())