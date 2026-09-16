# tests/test_trader_integration.py
"""
Integration tests: exercise the full trader loop
- Event deduplication
- LLM decisions
- Fund checks
- Trade execution
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Event
from app.simple_portfolio import SimplePortfolio
from app.llm_decider import LLMDecider
from app.main import load_cfg


async def test_llm_chinese_recognition():
    """Test LLM recognition of Chinese company names"""
    print("\n" + "="*70)
    print("Test 1: LLM recognition of Chinese company names")
    print("="*70)
    
    cfg = load_cfg()
    llm_cfg = cfg.get("llm", {})
    
    llm = LLMDecider(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
    )
    
    test_cases = [
        {
            "title": "36氪晚报 | 诺基亚与意大利电信达成5G合作",
            "expected_symbol": "NOK",
            "description": "Chinese news - Nokia"
        },
        {
            "title": "英伟达发布新一代AI芯片H200，性能提升10倍",
            "expected_symbol": "NVDA",
            "description": "Chinese news - NVIDIA"
        },
        {
            "title": "NVIDIA announces breakthrough H200 GPU",
            "expected_symbol": "NVDA",
            "description": "English news - NVIDIA"
        },
        {
            "title": "Arm custom chips get boost with Nvidia partnership",
            "expected_symbols": ["ARM", "NVDA"],
            "description": "English news - multiple companies"
        },
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- Test {i}: {case['description']} ---")
        print(f"Title: {case['title']}")
        
        try:
            decision = await llm.ask(case['title'], "")
            
            symbols = decision.get("symbols", [])
            action = decision.get("action", "")
            confidence = decision.get("confidence", 0)
            
            print(f"LLM response:")
            print(f"  Symbols: {symbols}")
            print(f"  Action: {action}")
            print(f"  Confidence: {confidence}")
            
            # Check whether the expected ticker(s) were recognized
            if "expected_symbols" in case:
                for expected in case["expected_symbols"]:
                    if expected in symbols:
                        print(f"✅ Recognized: {expected}")
                    else:
                        print(f"⚠️  Not recognized: {expected}")
            elif "expected_symbol" in case:
                if case["expected_symbol"] in symbols:
                    print(f"✅ Recognized: {case['expected_symbol']}")
                else:
                    print(f"❌ Failed: did not recognize {case['expected_symbol']}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        await asyncio.sleep(2)  # Avoid rate limiting


async def test_event_deduplication():
    """Test event deduplication"""
    print("\n" + "="*70)
    print("Test 2: Event deduplication")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Simulate an identical news event
    event_1 = Event(
        id="duplicate_event_123",
        ts_detected_utc=1000000,
        ts_published_utc=1000000,
        headline="NVIDIA announces H200",
        source="test",
        link="https://example.com/news1",
        market="us",
        symbols="NVDA",
        categories="tech",
        tags="#ai",
        score=95.0,
        pushed=0,
        expires_at_utc=2000000,
        thread_key="NVDA|tech"
    )
    
    # First pass
    print("\nFirst pass over the same event:")
    if not portfolio.is_event_processed(event_1.id):
        print(f"  Event {event_1.id[:20]}... not yet processed")
        print(f"  → OK to proceed with trading")
        portfolio.mark_event_processed(event_1.id)
        print(f"  → Marked as processed")
    else:
        print(f"  Event already processed, skipping")
    
    # Second pass (simulates encountering it again after a restart)
    print("\nSecond pass over the same event:")
    if not portfolio.is_event_processed(event_1.id):
        print(f"  ❌ Failed: should have been marked as processed")
    else:
        print(f"  ✅ Success: event already processed, trade skipped")


async def test_fund_checking():
    """Test fund checking"""
    print("\n" + "="*70)
    print("Test 3: Fund checking")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    trades = [
        {"symbol": "NVDA", "qty": 100, "price": 100.0, "should_pass": True},
        {"symbol": "TSLA", "qty": 200, "price": 100.0, "should_pass": True},
        {"symbol": "AAPL", "qty": 500, "price": 100.0, "should_pass": False},  # Exceeds cash
        {"symbol": "MSFT", "qty": 300, "price": 100.0, "should_pass": False},  # Exceeds reserve
    ]
    
    for i, trade in enumerate(trades, 1):
        print(f"\n--- Trade {i} ---")
        print(f"Attempting to buy: {trade['symbol']} x{trade['qty']} @ ${trade['price']:.2f}")
        print(f"Total cost: ${trade['qty'] * trade['price']:,.2f}")
        print(f"Current cash: ${portfolio.cash_balance:,.2f}")
        
        can_afford, reason = portfolio.can_afford(trade["qty"], trade["price"])
        
        if can_afford:
            print(f"✅ Can buy: {reason}")
            if trade["should_pass"]:
                # Simulate executing the buy
                portfolio.record_buy(
                    symbol=trade["symbol"],
                    quantity=trade["qty"],
                    price=trade["price"],
                    event_id=f"trade_{i}"
                )
                print(f"   Buy executed, remaining cash: ${portfolio.cash_balance:,.2f}")
        else:
            print(f"❌ Cannot buy: {reason}")
            if not trade["should_pass"]:
                print(f"   ✅ As expected (should be rejected)")


async def test_full_trading_flow():
    """Test the full trading flow"""
    print("\n" + "="*70)
    print("Test 4: Full trading flow")
    print("="*70)
    
    cfg = load_cfg()
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    llm_cfg = cfg.get("llm", {})
    llm = LLMDecider(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
    )
    
    # Simulate a news item
    event = Event(
        id="full_flow_test_001",
        ts_detected_utc=1000000,
        ts_published_utc=1000000,
        headline="英伟达发布革命性AI芯片H200，性能提升10倍",
        source="test",
        link="https://example.com/nvidia-h200",
        market="us",
        symbols="",  # Left empty so the LLM identifies it
        categories="tech",
        tags="#ai",
        score=95.0,
        pushed=0,
        expires_at_utc=2000000,
        thread_key="unknown"
    )
    
    print(f"\n📰 News event:")
    print(f"   Title: {event.headline}")
    print(f"   Score: {event.score}")
    print(f"   ID: {event.id}")
    
    # Step 1: Check whether the event was already processed
    print(f"\n🔍 Step 1: Check event deduplication")
    if portfolio.is_event_processed(event.id):
        print(f"   ⏭️  Event already processed, skipping")
        return
    else:
        print(f"   ✅ Event not yet processed, continuing")
    
    # Step 2: Call the LLM
    print(f"\n🤖 Step 2: Request LLM decision")
    try:
        decision = await llm.ask(event.headline, "")
        print(f"   LLM response: {decision}")
        
        action = decision.get("action", "").lower()
        symbols = decision.get("symbols", [])
        confidence = decision.get("confidence", 0)
        
        if not symbols:
            print(f"   ⏭️  LLM did not identify a ticker, skipping")
            return
        
        symbol = symbols[0]
        print(f"   ✅ Identified ticker: {symbol}")
        
        if action != "buy":
            print(f"   ⏭️  LLM decision is {action}, skipping")
            return
        
        if confidence < 60:
            print(f"   ⏭️  Confidence {confidence} < 60, skipping")
            return
        
        print(f"   ✅ LLM decision: BUY (confidence={confidence})")
        
    except Exception as e:
        print(f"   ❌ LLM call failed: {e}")
        return
    
    # Step 3: Fund check
    print(f"\n💰 Step 3: Fund check")
    qty = 100
    price = 100.0  # Estimated price
    
    can_afford, reason = portfolio.can_afford(qty, price)
    if not can_afford:
        print(f"   ⏭️  {reason}")
        return
    
    print(f"   ✅ Sufficient funds (cost: ${qty * price:,.2f})")
    
    # Step 4: Execute buy
    print(f"\n📈 Step 4: Execute buy")
    portfolio.record_buy(
        symbol=symbol,
        quantity=qty,
        price=price,
        event_id=event.id,
        reason=decision.get("reason", "")
    )
    
    # Step 5: Mark event as processed
    print(f"\n✅ Step 5: Mark event as processed")
    portfolio.mark_event_processed(event.id)
    
    # Show summary
    print(f"\n📊 Trade summary:")
    summary = portfolio.get_summary()
    print(f"   Remaining cash: ${summary['cash_balance']:,.2f}")
    print(f"   Used: {summary['cash_usage_pct']:.1%}")
    print(f"   Number of trades: {summary['num_trades']}")


async def test_duplicate_prevention():
    """Test duplicate trade prevention"""
    print("\n" + "="*70)
    print("Test 5: Duplicate trade prevention")
    print("="*70)
    
    portfolio = SimplePortfolio(initial_capital=100000.0)
    
    # Simulate the first trade
    event_id = "prevent_dup_001"
    
    print("\nFirst trade:")
    if not portfolio.is_event_processed(event_id):
        print(f"  ✅ Event not yet processed, executing trade")
        portfolio.record_buy("NVDA", 100, 100.0, event_id=event_id)
        portfolio.mark_event_processed(event_id)
        print(f"  Remaining cash: ${portfolio.cash_balance:,.2f}")
    
    # Simulate encountering the same event again (after restart)
    print("\nSame event encountered again:")
    if not portfolio.is_event_processed(event_id):
        print(f"  ❌ Failed: duplicate trade should have been prevented")
        portfolio.record_buy("NVDA", 100, 100.0, event_id=event_id)
    else:
        print(f"  ✅ Success: duplicate trade prevented")
        print(f"  Remaining cash: ${portfolio.cash_balance:,.2f} (unchanged)")


async def main():
    """Run all integration tests"""
    print("\n" + "="*80)
    print("🧪 Trader Integration Test Suite")
    print("="*80)
    
    try:
        await test_llm_chinese_recognition()
        await test_event_deduplication()
        await test_fund_checking()
        await test_full_trading_flow()
        await test_duplicate_prevention()
        
        print("\n" + "="*80)
        print("✅ All integration tests completed!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())