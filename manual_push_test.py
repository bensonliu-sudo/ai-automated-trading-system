import asyncio
import time
from app.models import Event
from app.notifier import Notifier

async def test_push():
    # Use the simplest config, enabling only the Telegram channel
    n = Notifier({
    "notify_channels": ["telegram"],
    "retry": {"max_times": 3, "backoff_sec": 2},  # 👈 pass a dict
})

    now = int(time.time() * 1000)
    ev = Event(
        id=f"manual_test_{now}",
        ts_detected_utc=now,
        ts_published_utc=now,
        headline=f"[MANUAL TEST] Hello from manual push {now}",
        source="manual",
        link="https://example.com",
        market="us",
        symbols="TEST",
        categories="unit",
        tags="#manual",
        score=99.9,
        pushed=0,
        expires_at_utc=now + 600_000,
        thread_key=f"manual_{now}",
    )

    ok = await n.push(ev)
    print("manual push ok:", ok)

if __name__ == "__main__":
    asyncio.run(test_push())