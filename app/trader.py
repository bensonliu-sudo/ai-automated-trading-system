# app/trader.py

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from ib_insync import IB, Stock, MarketOrder


class IBKRTrader:
    """
    A simple but reasonably safe IBKR wrapper:
    - Supports dry_run (print only, no real orders)
    - Manages the connect / disconnect lifecycle
    - Uses asyncio + a thread pool with ib_insync's synchronous API
    - Maintains an internal positions snapshot to avoid duplicate buys
    """

    def __init__(self, cfg: Dict, *, dry_run: bool = True) -> None:
        self.host: str = cfg.get("host", "127.0.0.1")
        self.port: int = int(cfg.get("port", 4002))
        self.client_id: int = int(cfg.get("client_id", 1))
        self.dry_run: bool = dry_run

        self.ib: IB = IB()
        self.connected: bool = False
        self.portfolio = None
        self.dry_run = dry_run

        # symbol -> {"qty": float, "avg_price": float}
        self.positions: Dict[str, Dict[str, float]] = {}

        # Serialize operations to prevent concurrent orders
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Connect to IBKR (TWS or Gateway)."""
        if self.connected:
            return

        # ⭐ Use ib_insync's async API directly, no executor
        await self.ib.connectAsync(self.host, self.port, clientId=self.client_id, timeout=5)

        self.connected = True
        print(
            f"[IBKR] Connected to {self.host}:{self.port}, "
            f"clientId={self.client_id}, dry_run={self.dry_run}"
        )
        # === Set market data type ===
        # 3 = delayed market data
        try:
            self.ib.reqMarketDataType(1)
            print("[IBKR] Using real-time market data (type=1)")
        except Exception as e:
            print("[IBKR] Failed to set real-time market data type:", e)
        await self.refresh_positions()

    async def close(self) -> None:
        """
        Call while the event loop is still alive to disconnect cleanly.
        Only needs to be called once in the finally block of main():
            await trader.close()
        """
        if not self.connected:
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.ib.disconnect)
        self.connected = False
        print("[IBKR] Disconnected")

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------
    async def get_last_price(self, symbol: str) -> float:
        """
        Request the latest market price from IBKR.
        Requires market data permissions in TWS / Gateway (paper accounts have them by default).
        """
        from ib_insync import Stock

        contract = Stock(symbol, "SMART", "USD")
        ticker = self.ib.reqMktData(contract, "", False, False)

        # Wait for price update
        for _ in range(50):  # wait at most 5 seconds
            await asyncio.sleep(0.1)
            if ticker.last > 0:
                return float(ticker.last)
            if ticker.close > 0:
                return float(ticker.close)

        raise RuntimeError(f"Couldn't get {symbol} information (no data or unauthorized)")
    
    async def refresh_positions(self) -> None:
        """Fetch all current positions from IBKR and update self.positions."""
        if not self.connected:
            return

        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, self.ib.positions)

        self.positions.clear()
        for p in positions:
            symbol = p.contract.symbol
            self.positions[symbol] = {
                "qty": float(p.position),
                "avg_price": float(p.avgCost),
            }

        print("[IBKR] Positions:", self.positions)

    def has_position(self, symbol):
        return symbol in self.positions and self.positions[symbol]["qty"] > 0

    async def get_position(self, symbol: str) -> int:
        """
        Return the current position size for a symbol.
        For safety, refresh positions (re-read from TWS) before each call.
        """
        await self.refresh_positions()
        pos = self.positions.get(symbol)
        if not pos:
            return 0
        return pos["qty"]

    # ------------------------------------------------------------------
    # Order wrappers
    # ------------------------------------------------------------------
    # async def _place_order(self, symbol: str, action: str, qty: int) -> bool:
    #     """
    #     Low-level order placement, handles both BUY / SELL.
    #     Called by buy()/sell().
    #     """
    #     if not self.connected:
    #         print("[IBKR] Not connected; cannot place order")
    #         return False

    #     async with self._lock:
    #         action = action.upper()
    #         contract = Stock(symbol, "SMART", "USD")
    #         order = MarketOrder(action, qty)

    #         if self.dry_run:
    #             print(f"[IBKR][DRY] {action} {qty} {symbol}")
    #             return True

    #         loop = asyncio.get_event_loop()

    #         def _do_place():
    #             trade = self.ib.placeOrder(contract, order)
    #             # Give TWS a moment to update status (optional)
    #             self.ib.sleep(0.1)
    #             return trade

    #         trade = await loop.run_in_executor(None, _do_place)
    #         print(
    #             f"[IBKR] Sent order {action} {qty} {symbol}, "
    #             f"status={trade.orderStatus.status}"
    #         )

    #         # Refresh the positions snapshot
    #         await self.refresh_positions()
    #         return True

    # async def buy(self, symbol: str, qty: int = 1) -> bool:
    #     """Buy if there is no current position."""
    #     if self.has_position(symbol):
    #         print(f"[IBKR] Already holding {symbol}, skip buy")
    #         return False

    #     print(f"[IBKR] BUY {symbol} x{qty}")
    #     return await self._place_order(symbol, "BUY", qty)
    # Inside the IBKRTrader class in app/trader.py

    async def buy(self, symbol: str, qty: int) -> bool:
        """
        Place a buy order (supports dry_run; real orders use ib_insync's async style)

        Returns:
            True  order succeeded (submitted/filled)
            False failed/rejected
        """
        # 1) Dry run: only update the simulated position, no API call
        if self.dry_run:
            print(f"[IBKR][DRY] simulated buy {symbol} x {qty}")
            if self.portfolio is not None:
                self.portfolio.buy(symbol, qty, estimated_price=100.0)  # price logic already exists elsewhere
            return True

        # 2) Real order: call placeOrder directly in the current coroutine, not via run_in_executor
        print(f"[IBKR] BUY {symbol} x {qty}")

        # Build contract
        contract = Stock(symbol, "SMART", "USD")

        # Optional: qualify first to make sure the contract is valid
        try:
            qualified = await self.ib.qualifyContractsAsync(contract)
            if qualified:
                contract = qualified[0]
        except Exception as e:
            print("[IBKR] qualifyContracts failed:", e)

        # Market order
        order = MarketOrder("BUY", qty)

        order.outsideRth = True

        # Send order (non-blocking, returns a Trade object immediately)
        trade = self.ib.placeOrder(contract, order)
        print(f"[IBKR] order sent, orderId={trade.order.orderId}")

        # 3) Wait for fill/status update (async wait)
        try:
            while not trade.isDone():
                await self.ib.sleep(0.5)  # does not block the event loop

            status = trade.orderStatus.status
            filled = trade.orderStatus.filled
            avg_fill_price = trade.orderStatus.avgFillPrice

            print(
                f"[IBKR] order complete: status={status}, "
                f"filled={filled}, avg_price={avg_fill_price}"
            )

            # The following statuses count as success
            return status in ("Filled", "Submitted", "PreSubmitted")
        except Exception as e:
            print("[IBKR] error while waiting for order status:", e)
            return False

    async def sell(self, symbol: str, qty: Optional[int] = None) -> bool:
        """
        Sell a position. Sells the full position by default; if qty is given, sells min(qty, current position).
        """
        if not self.has_position(symbol):
            print(f"[IBKR] No position in {symbol}, skip sell")
            return False

        position_qty = int(self.positions[symbol]["qty"])
        real_qty = position_qty if qty is None else min(qty, position_qty)

        if real_qty <= 0:
            print(f"[IBKR] Computed sell qty <= 0 for {symbol}, skip")
            return False

        print(f"[IBKR] SELL {symbol} x{real_qty}")
        return await self._place_order(symbol, "SELL", real_qty)

    # ------------------------------------------------------------------
    # Simple take-profit / stop-loss logic (optional)
    # ------------------------------------------------------------------
    async def evaluate_close(
        self,
        symbol: str,
        current_price: float,
        *,
        take_profit: float = 0.10,   # +10%
        stop_loss: float = -0.10,    # -10%
    ) -> bool:
        """
        Decide from the current price whether the position should be closed:
        - profit exceeds take_profit
        - or loss exceeds stop_loss
        Returns True if a close was triggered (or a simulated close in dry_run mode).
        """
        if not self.has_position(symbol):
            return False

        pos = self.positions[symbol]
        entry = pos["avg_price"]
        pnl_pct = (current_price - entry) / entry

        print(
            f"[IBKR] {symbol} PnL {pnl_pct:.2%} "
            f"(entry={entry:.2f}, current={current_price:.2f})"
        )

        if pnl_pct >= take_profit or pnl_pct <= stop_loss:
            print(f"[IBKR] {symbol} hit exit condition, closing...")
            await self.sell(symbol)
            return True

        return False