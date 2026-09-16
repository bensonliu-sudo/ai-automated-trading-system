# tests/test_simple_portfolio.py
"""
Test all SimplePortfolio functionality
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.simple_portfolio import SimplePortfolio


def test_initialization():
    """Test initialization"""
    print("\n" + "="*70)
    print("Test 1: Initialization")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    assert portfolio.initial_capital == 100000.0
    assert portfolio.cash_balance == 100000.0
    assert len(portfolio.processed_events) == 0
    assert len(portfolio.trades) == 0
    
    print("✅ Initialization succeeded")
    print(f"   Initial capital: ${portfolio.initial_capital:,.2f}")
    print(f"   Current cash: ${portfolio.cash_balance:,.2f}")


def test_event_processing():
    """Test event deduplication"""
    print("\n" + "="*70)
    print("Test 2: Event deduplication")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # First check
    event_id = "test_event_123"
    assert not portfolio.is_event_processed(event_id)
    print(f"✅ Event {event_id} not processed (first check)")
    
    # Mark as processed
    portfolio.mark_event_processed(event_id)
    print(f"✅ Marked event {event_id} as processed")
    
    # Second check
    assert portfolio.is_event_processed(event_id)
    print(f"✅ Event {event_id} processed (second check)")
    
    # Test another event
    event_id_2 = "test_event_456"
    assert not portfolio.is_event_processed(event_id_2)
    print(f"✅ Event {event_id_2} not processed")


def test_can_afford():
    """Test fund checking"""
    print("\n" + "="*70)
    print("Test 3: Fund checking")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Case 1: Can buy
    can_buy, reason = portfolio.can_afford(quantity=100, estimated_price=100.0)
    assert can_buy == True
    print(f"✅ Can buy: 100 shares @ $100 = $10,000 (reason: {reason})")
    
    # Case 2: Amount too large
    can_buy, reason = portfolio.can_afford(quantity=1000, estimated_price=100.0)
    assert can_buy == False
    print(f"✅ Cannot buy: 1000 shares @ $100 = $100,000 (reason: {reason})")
    
    # Case 3: Buy would dip into the cash reserve
    can_buy, reason = portfolio.can_afford(quantity=900, estimated_price=100.0)
    assert can_buy == False
    print(f"✅ Cannot buy: 900 shares @ $100 = $90,000 (reason: {reason})")
    
    # Case 4: Boundary case
    can_buy, reason = portfolio.can_afford(quantity=850, estimated_price=100.0)
    print(f"   Buy 850 shares @ $100: {'allowed' if can_buy else 'rejected'} ({reason})")


def test_record_buy():
    """Test buy recording"""
    print("\n" + "="*70)
    print("Test 4: Buy recording")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Record the first buy
    portfolio.record_buy(
        symbol="NVDA",
        quantity=100,
        price=100.0,
        event_id="event_001",
        reason="AI chip breakthrough"
    )
    
    assert portfolio.cash_balance == 90000.0
    assert len(portfolio.trades) == 1
    print(f"✅ Recorded buy: NVDA x100 @ $100")
    print(f"   Remaining cash: ${portfolio.cash_balance:,.2f}")
    print(f"   Trade records: {len(portfolio.trades)}")
    
    # Record the second buy
    portfolio.record_buy(
        symbol="TSLA",
        quantity=50,
        price=200.0,
        event_id="event_002",
        reason="Record deliveries"
    )
    
    assert portfolio.cash_balance == 80000.0
    assert len(portfolio.trades) == 2
    print(f"✅ Recorded buy: TSLA x50 @ $200")
    print(f"   Remaining cash: ${portfolio.cash_balance:,.2f}")
    print(f"   Trade records: {len(portfolio.trades)}")


def test_record_sell():
    """Test sell recording"""
    print("\n" + "="*70)
    print("Test 5: Sell recording")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Buy first
    portfolio.record_buy("NVDA", 100, 100.0)
    print(f"   Cash after buy: ${portfolio.cash_balance:,.2f}")
    
    # Then sell
    portfolio.record_sell(
        symbol="NVDA",
        quantity=100,
        price=120.0,
        event_id="event_sell_001",
        reason="Take profit"
    )
    
    assert portfolio.cash_balance == 102000.0  # 90000 + 12000
    assert len(portfolio.trades) == 2
    print(f"✅ Recorded sell: NVDA x100 @ $120")
    print(f"   Cash after sell: ${portfolio.cash_balance:,.2f}")
    print(f"   Profit: ${portfolio.cash_balance - portfolio.initial_capital:,.2f}")


def test_get_summary():
    """Test summary information"""
    print("\n" + "="*70)
    print("Test 6: Summary information")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Execute a few trades
    portfolio.record_buy("NVDA", 100, 100.0, event_id="e1")
    portfolio.record_buy("TSLA", 50, 200.0, event_id="e2")
    portfolio.mark_event_processed("e1")
    portfolio.mark_event_processed("e2")
    
    summary = portfolio.get_summary()
    
    print(f"✅ Summary:")
    print(f"   Initial capital: ${summary['initial_capital']:,.2f}")
    print(f"   Current cash: ${summary['cash_balance']:,.2f}")
    print(f"   Capital used: ${summary['total_spent']:,.2f}")
    print(f"   Capital usage: {summary['cash_usage_pct']:.1%}")
    print(f"   Number of trades: {summary['num_trades']}")
    print(f"   Processed events: {summary['num_processed_events']}")
    
    assert summary['total_spent'] == 20000.0
    assert summary['cash_usage_pct'] == 0.20
    assert summary['num_trades'] == 2
    assert summary['num_processed_events'] == 2


def test_cache_cleanup():
    """Test cache cleanup"""
    print("\n" + "="*70)
    print("Test 7: Cache cleanup (add 1050 events)")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Add 1050 events (exceeds the 1000 limit)
    for i in range(1050):
        portfolio.mark_event_processed(f"event_{i:04d}")
    
    # Only 950 should remain (the oldest 100 were removed)
    assert len(portfolio.processed_events) == 950
    print(f"✅ Cache cleaned up automatically")
    print(f"   Added: 1050 events")
    print(f"   Retained: {len(portfolio.processed_events)} events")
    print(f"   Removed: 100 old events")
    
    # Verify the oldest event was removed
    assert not portfolio.is_event_processed("event_0000")
    print(f"✅ Oldest event event_0000 was removed")
    
    # Verify the newest event still exists
    assert portfolio.is_event_processed("event_1049")
    print(f"✅ Newest event event_1049 still exists")


def test_print_summary():
    """Test summary printing"""
    print("\n" + "="*70)
    print("Test 8: Print summary")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    portfolio.record_buy("NVDA", 100, 100.0)
    portfolio.record_buy("TSLA", 50, 200.0)
    portfolio.record_sell("NVDA", 50, 110.0)
    
    portfolio.print_summary()


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 SimplePortfolio Test Suite")
    print("="*80)
    
    try:
        test_initialization()
        test_event_processing()
        test_can_afford()
        test_record_buy()
        test_record_sell()
        test_get_summary()
        test_cache_cleanup()
        test_print_summary()
        
        print("\n" + "="*80)
        print("✅ All tests passed!")
        print("="*80 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()