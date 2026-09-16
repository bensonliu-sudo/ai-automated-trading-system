# app/simple_portfolio.py
"""
Simplified portfolio management - minimal viable version
- Track cash balance
- Record processed events
- Basic risk checks

Compatible with Python 3.8+
"""
from typing import Tuple, Dict, List, Set
from collections import deque
from typing import Deque

class SimplePortfolio:
    """Simple portfolio manager"""
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize the portfolio
        
        Args:
            initial_capital: initial capital, default $100,000
        """
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital

        # Processed events: a set + an ordered queue
        self.processed_events: Set[str] = set()         # for O(1) is_event_processed
        self._processed_order: Deque[str] = deque()     # records insertion order, used for cleanup

        self.trades: List[Dict] = []  # trade records
        
        print(f"[portfolio] Initial fund ${self.initial_capital:,.2f}")
        
    def is_event_processed(self, event_id: str) -> bool:
        """
        Check whether an event has been processed
        
        Args:
            event_id: event ID
            
        Returns:
            True: processed, False: not processed
        """
        return event_id in self.processed_events
    
    def mark_event_processed(self, event_id: str) -> None:
        """
        Mark an event as processed (FIFO cleanup)
        """

        # Skip if already recorded
        if event_id in self.processed_events:
            return
        
        # Add
        self.processed_events.add(event_id)
        self._processed_order.append(event_id)

        # Cleanup logic
        MAX_EVENTS = 1000
        CLEAN_SIZE = 100

        if len(self.processed_events) > MAX_EVENTS:
            removed = 0
            while removed < CLEAN_SIZE and self._processed_order:
                old_id = self._processed_order.popleft()
                if old_id in self.processed_events:
                    self.processed_events.remove(old_id)
                    removed += 1

            print(f"[portfolio] cleaning cache: moved {removed} expired event")
    
    def can_afford(self, quantity: int, estimated_price: float) -> Tuple[bool, str]:
        """
        Check whether there is enough cash to buy
        """
        total_cost = quantity * estimated_price

        # Check 1: is the cash balance sufficient
        if self.cash_balance < total_cost:
            return False, f"Inadequate fund:  ${total_cost:,.2f} needed,  ${self.cash_balance:,.2f} available"

        # Check 2: keep a 10% cash reserve (must be strictly above 10%; equal is not allowed)
        min_reserve = self.initial_capital * 0.10
        remaining = self.cash_balance - total_cost
        if remaining <= min_reserve:
            return (
                False,
                f"Inadequate cash: rest after trade ${remaining:,.2f} <= min threshold ${min_reserve:,.2f}",
            )

        return True, "OK"
    
    def record_buy(self, symbol: str, quantity: int, price: float, event_id: str = "", reason: str = "") -> None:
        """
        Record a buy trade
        
        Args:
            symbol: ticker symbol
            quantity: quantity bought
            price: buy price
            event_id: event ID
            reason: reason for buying
        """
        cost = quantity * price
        self.cash_balance -= cost
        
        trade = {
            "timestamp": int(__import__("time").time() * 1000),
            "event_id": event_id,
            "symbol": symbol,
            "action": "buy",
            "quantity": quantity,
            "price": price,
            "total": cost,
            "reason": reason
        }
        self.trades.append(trade)
        
        print(f"[portfolio] 📈 Purchased: {symbol} x{quantity} @ ${price:.2f} = ${cost:,.2f}")
        print(f"[portfolio] 💰 Rest Money: ${self.cash_balance:,.2f}")
    
    def record_sell(self, symbol: str, quantity: int, price: float, event_id: str = "", reason: str = "") -> None:
        """
        Record a sell trade
        
        Args:
            symbol: ticker symbol
            quantity: quantity sold
            price: sell price
            event_id: event ID
            reason: reason for selling
        """
        proceeds = quantity * price
        self.cash_balance += proceeds
        
        trade = {
            "timestamp": int(__import__("time").time() * 1000),
            "event_id": event_id,
            "symbol": symbol,
            "action": "sell",
            "quantity": quantity,
            "price": price,
            "total": proceeds,
            "reason": reason
        }
        self.trades.append(trade)
        
        print(f"[portfolio] 📉 sold: {symbol} x{quantity} @ ${price:.2f} = ${proceeds:,.2f}")
        print(f"[portfolio] 💰 current cash: ${self.cash_balance:,.2f}")
    
    def get_summary(self) -> Dict:
        """
        Get portfolio summary
        
        Returns:
            Dictionary containing account information
        """
        total_spent = self.initial_capital - self.cash_balance
        cash_usage_pct = total_spent / self.initial_capital if self.initial_capital > 0 else 0
        
        return {
            "initial_capital": self.initial_capital,
            "cash_balance": self.cash_balance,
            "total_spent": total_spent,
            "cash_usage_pct": cash_usage_pct,
            "num_trades": len(self.trades),
            "num_processed_events": len(self.processed_events)
        }
    
    def print_summary(self) -> None:
        """Print portfolio summary"""
        summary = self.get_summary()
        
        print("\n" + "="*70)
        print("📊 portfolio summary")
        print("="*70)
        print(f"Initial fund:     ${summary['initial_capital']:>15,.2f}")
        print(f"Current fund:     ${summary['cash_balance']:>15,.2f}")
        print(f"Used fund:   ${summary['total_spent']:>15,.2f}  ({summary['cash_usage_pct']:.1%})")
        print(f"Number of trades:     {summary['num_trades']:>15}")
        print(f"Handled events:   {summary['num_processed_events']:>15}")
        print("="*70 + "\n")
    
    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """
        Get recent trade records
        
        Args:
            limit: number of records to return
            
        Returns:
            List of trade records
        """
        return self.trades[-limit:] if self.trades else []