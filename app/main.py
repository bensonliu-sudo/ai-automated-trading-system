# app/main.py
# collector -> scorer -> (fanout) -> trader + notifier -> housekeeper

from __future__ import annotations
import asyncio
import time
import sys
from pathlib import Path
import yaml
import os

from app.trader import IBKRTrader

from app.llm_decider import LLMDecider

ROOT = Path(__file__).resolve().parents[1]  # intel-hub/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .collector import run_collectors
from .scorer import run_scorer
from .notifier import Notifier
from .storage import init_db, delete_expired
from .models import Event


DEFAULT_CFG = {
    "notifier": {
        "schema_version": 1,
        "display_timezone": "Australia/Sydney",
        "retention_hours": 48,
        "dedupe_minutes": 15,
        "critical_threshold": 70,
        "important_threshold": 30,
        "translate_to_zh": False,
        "storage": "sqlite",
        "notify_channels": ["telegram"],
        "debug_startup_push": False,
    }
}


def load_cfg() -> dict:
    """ops/config.yml is optional; fall back to defaults if missing."""
    cfg_path = ROOT / "ops" / "config.yml"
    if cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            out = {**DEFAULT_CFG, **data}
            if "notifier" in data:
                out["notifier"] = {
                    **DEFAULT_CFG["notifier"],
                    **(data.get("notifier") or {}),
                }
            return out
        except Exception as e:
            print(f"[main] couldn't read ops/config.yml, using default. err={e}")
    return DEFAULT_CFG


# ====================== Trader loop ======================

# Replace run_trader_loop in main.py
# Add more detailed logging showing why each event is skipped

# Fixed run_trader_loop
# Replaces the corresponding function in app/main.py

async def run_trader_loop(q_scored: "asyncio.Queue", cfg: dict):
    """
    Consume high-score Events from the queue -> LLM decision -> IBKR order
    
    Integrated features:
    - Event dedupe (prevents trading the same news multiple times)
    - Cash check (prevents overdraft)
    - LLM ticker symbol recognition (supports Chinese and English)
    - Position management
    """
    from app.simple_portfolio import SimplePortfolio  # ⭐ import
    
    trader_cfg = cfg.get("trader", {})
    if not trader_cfg.get("enable", False):
        print("[trader] disabled")
        return

    # ⭐ Initialize portfolio manager
    initial_capital = trader_cfg.get("initial_capital", 100000.0)
    portfolio = SimplePortfolio(initial_capital=initial_capital)

    # 1. Initialize LLM
    llm_cfg = cfg["llm"]
    llm = LLMDecider(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
    )

    # 2. Initialize IBKR Trader
    trader = IBKRTrader(trader_cfg["ibkr"], dry_run=trader_cfg.get("dry_run", True))
    await trader.connect()

    buy_thr = trader_cfg.get("buy_threshold", 70)
    max_per_symbol = trader_cfg.get("max_position_per_symbol", 100)

    print("[trader] started with portfolio management")
    print(f"[trader]   buy_threshold = {buy_thr}")
    print(f"[trader]   max_position_per_symbol = {max_per_symbol}")
    print(f"[trader]   dry_run = {trader_cfg.get('dry_run', True)}")
    
    event_count = 0

    while True:
        ev = await q_scored.get()
        event_count += 1
        
        try:
            event_id = ev.id
            title = ev.headline
            score = ev.score
            
            print(f"\n[trader] >>> event #{event_count}")
            print(f"[trader]     ID: {event_id[:30]}...")
            print(f"[trader]     Headline: {title[:80]}...")
            print(f"[trader]     Score: {score}")

            # ⭐ 0) Check whether the event was already processed (prevent duplicate trades)
            if portfolio.is_event_processed(event_id):
                print(f"[trader] ⏭️  pass: already handled (no repeat trade)")
                continue

            # 1) Skip low scores
            if score < buy_thr:
                print(f"[trader] ⏭️  pass: score={score} < buy_threshold={buy_thr}")
                continue
            
            print(f"[trader] ✓ marks qualified: {score} >= {buy_thr}")

            # ⭐ 2) Call the LLM directly (let the LLM identify ticker symbols, supports Chinese and English)
            print(f"[trader] 🤖 using LLM ...")
            decision = await llm.ask(
                news_title=title,
                news_body=getattr(ev, "summary", "") or getattr(ev, "body", ""),
            )
            print(f"[trader] 📊 LLM return: {decision}")

            action = (decision.get("action") or "").lower()
            conf = decision.get("confidence", 0)
            llm_syms = decision.get("symbols") or []
            
            # ⭐ Get ticker symbol from the LLM
            if not llm_syms:
                print(f"[trader] ⏭️  pass: LLM couldn't get stock")
                continue
            
            base_symbol = llm_syms[0]
            print(f"[trader] ✓ LLM get stock: {base_symbol}")

            # 3) Only handle buy
            if action != "buy":
                print(f"[trader] ⏭️  pass: LLM action={action} (no buy)")
                continue
            
            if conf < 60:
                print(f"[trader] ⏭️  pass: LLM confidence={conf} < 60")
                continue
            
            print(f"[trader] ✓ LLM decision: BUY (confidence={conf})")

            # 4) Position control
            print(f"[trader] 🔍 check position...")
            pos = await trader.get_position(base_symbol)
            print(f"[trader] current position: {base_symbol} = {pos}")
            
            if pos >= max_per_symbol:
                print(f"[trader] ⏭️  pass: position full {pos} >= {max_per_symbol}")
                continue
            
            qty = max_per_symbol - pos
            print(f"[trader] ✓ purchasable amount: {qty}")

            # ⭐ 5) Cash check (prevent overdraft)
            # Estimate price (should really fetch a live price)
            estimated_price = await trader.get_last_price(base_symbol)  # TODO: fetch live price
            
            can_afford, reason = portfolio.can_afford(qty, estimated_price)
            if not can_afford:
                print(f"[trader] ⏭️  pass purchase: {reason}")
                continue
            
            print(f"[trader] ✓ enough budget (estimate cost: ${qty * estimated_price:,.2f})")

            # 6) Execute buy
            print(f"[trader] 💰 BUY {base_symbol} x {qty}")
            print(f"[trader]    score={score}, confidence={conf}")
            success = await trader.buy(base_symbol, qty)
            
            if success:
                # ⭐ Record the trade
                portfolio.record_buy(
                    symbol=base_symbol,
                    quantity=qty,
                    price=estimated_price,
                    event_id=event_id,
                    reason=decision.get("reason", "")
                )
                
                # ⭐ Mark event as processed
                portfolio.mark_event_processed(event_id)
                
                print(f"[trader] ✅ BUY successfully: {base_symbol} x {qty}")
                
                # Show portfolio summary
                summary = portfolio.get_summary()
                print(f"[portfolio] 💰 MONEY REST: ${summary['cash_balance']:,.2f} / ${summary['initial_capital']:,.2f}")
                print(f"[portfolio] 📊 MONEY USED: {summary['cash_usage_pct']:.1%}, has traded: {summary['num_trades']} times")
            else:
                print(f"[trader] ⚠️  Fail to buy: {base_symbol}")

        except Exception as e:
            print(f"[trader] ❌ error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            q_scored.task_done()  # ⭐ call only once, here


# ====================== Notifier loop ======================

async def run_notifier_loop(q_scored: "asyncio.Queue", db, notifier_cfg: dict):
    """
    Consume Events from the queue and hand them to the Notifier for pushing.
    """
    if "notifier" in notifier_cfg:
        notifier_cfg = notifier_cfg["notifier"]

    print("[notifier] started")
    notifier = Notifier(notifier_cfg)

    # ---- Startup sanity push ----
    startup_flag = bool(notifier_cfg.get("debug_startup_push", False))
    print(f"[notifier] debug_startup_push={startup_flag}")

    if startup_flag:
        now = int(time.time() * 1000)
        ev = Event(
            id=f"boot_sanity_{now}",
            ts_detected_utc=now,
            ts_published_utc=now,
            headline="(BOOT SANITY) Intel Hub notifier is online ✅",
            source="unit_test",
            link="https://example.com",
            market="us",
            symbols="OPEN",
            categories="contract",
            tags="#sanity",
            score=95.0,
            pushed=0,
            expires_at_utc=now + 3600_000,
            thread_key=f"BOOT|{now}",
        )
        ok = await notifier.push(ev)
        print(f"[notifier] startup sanity push -> {ok}")

    try:
        while True:
            ev = await q_scored.get()
            try:
                ok = await notifier.push(ev)
                if not ok:
                    # Print here if needed
                    pass
            except Exception as e:
                print(f"[notifier] push error: {e}")
            finally:
                q_scored.task_done()
    except asyncio.CancelledError:
        print("[notifier] cancelled")
        raise
    finally:
        print("[notifier] finished")

# async def run_position_monitor(trader, interval_sec=60):
#     """
#     Periodically monitor positions and execute take-profit/stop-loss
#     """
#     print(f"[monitor] starting position monitor (interval {interval_sec}s)")
    
#     # A method to fetch live prices is needed here
#     # Since IBKR requires a live data subscription, use simple logic for now
    
#     try:
#         while True:
#             await asyncio.sleep(interval_sec)
            
#             await trader.refresh_positions()
            
#             if not trader.positions:
#                 print("[monitor] no positions")
#                 continue
            
#             print(f"\n[monitor] checking {len(trader.positions)} positions...")
            
#             for symbol, pos_info in list(trader.positions.items()):
#                 if pos_info["qty"] <= 0:
#                     continue
                
#                 # TODO: fetch current market price
#                 # Live price fetching logic needs to be implemented here
#                 # current_price = await get_market_price(symbol)
                
#                 # Skip for now since there is no live price data
#                 print(f"[monitor] {symbol}: qty={pos_info['qty']}, avg_price={pos_info['avg_price']}")
                
#                 # If a live price is available, execute take-profit/stop-loss
#                 # await trader.evaluate_close(
#                 #     symbol,
#                 #     current_price,
#                 #     take_profit=0.10,  # +10%
#                 #     stop_loss=-0.05    # -5%
#                 # )
    
#     except asyncio.CancelledError:
#         print("[monitor] cancelled")
#         raise
#     finally:
#         print("[monitor] finished")
# ====================== Housekeeper ======================

async def run_housekeeper(db, every_sec: int = 600):
    """Periodically purge expired events."""
    print("[housekeeper] started")
    try:
        while True:
            try:
                now_ms = int(time.time() * 1000)
                await delete_expired(db, now_ms)
            except Exception as e:
                print(f"[housekeeper] delete_expired error: {e}")
            await asyncio.sleep(every_sec)
    except asyncio.CancelledError:
        print("[housekeeper] cancelled")
        raise
    finally:
        print("[housekeeper] finished")


# ====================== Fanout: scorer -> trader + notifier ======================

async def fanout_scored(
    q_in: "asyncio.Queue",
    q_notify: "asyncio.Queue",
    q_trade: "asyncio.Queue",
):
    """
    Consume only q_in, then copy each event to q_notify and q_trade.
    Ensures the scorer only needs to maintain a single output queue.
    """
    print("[fanout] started")
    try:
        while True:
            ev = await q_in.get()
            
            # ⭐ Added this log line
            print(f"[fanout] >>> received event: {ev.id}, score={ev.score}, headline={ev.headline[:50]}...")
            
            try:
                if q_notify is not None:
                    await q_notify.put(ev)
                    print(f"[fanout]   → sent to q_notify")  # ⭐ added
                
                if q_trade is not None:
                    await q_trade.put(ev)
                    print(f"[fanout]   → sent to q_trade")   # ⭐ added
            finally:
                q_in.task_done()
    except asyncio.CancelledError:
        print("[fanout] cancelled")
        raise
    finally:
        print("[fanout] finished")


# ====================== main ======================

async def main(run_seconds: int = 30):
    cfg = load_cfg()
    db = await init_db(ROOT / "intel.db")

    # Raw news queue
    q_raw: asyncio.Queue = asyncio.Queue()

    # Scorer output (master queue)
    q_scored_master: asyncio.Queue = asyncio.Queue()

    # Two fanout queues: one for notifications, one for trading
    q_notify: asyncio.Queue = asyncio.Queue()
    q_trade: asyncio.Queue = asyncio.Queue()

    tasks = []
    print("[main] creating tasks…")

    # 1) Collectors -> q_raw
    tasks.append(asyncio.create_task(run_collectors(q_raw)))
    print("[collector] started")

    # 2) Scorer: q_raw -> q_scored_master (+ DB)
    tasks.append(asyncio.create_task(run_scorer(q_raw, q_scored_master, db)))
    print("[scorer] started")

    # 3) Fanout: q_scored_master -> q_notify + q_trade
    tasks.append(asyncio.create_task(fanout_scored(q_scored_master, q_notify, q_trade)))

    # 4) Trading
    tasks.append(asyncio.create_task(run_trader_loop(q_trade, cfg)))

    # 5) Notifications
    tasks.append(asyncio.create_task(run_notifier_loop(q_notify, db, cfg)))

    # 6) Housekeeper
    tasks.append(asyncio.create_task(run_housekeeper(db, every_sec=600)))

    # tasks.append(asyncio.create_task(run_position_monitor(trader, interval_sec=300)))

    print(f"[main] running for {run_seconds}s …")

    try:
        if run_seconds and run_seconds > 0:
            await asyncio.sleep(run_seconds)
        else:
            stop = asyncio.Event()
            await stop.wait()   # run forever
    except asyncio.CancelledError:
        print("[main] cancelled")
        raise
    finally:
        # Graceful shutdown
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[main] finished")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-seconds", type=int, default=0)
    args = parser.parse_args()

    asyncio.run(main(run_seconds=args.run_seconds))