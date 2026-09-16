# tests/test_push.py
# Manual smoke test for the Telegram notifier. Requires TELEGRAM_BOT_TOKEN
# and TELEGRAM_CHAT_ID in the environment.
import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from app.notifier import _TelegramAdapter

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

async def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first.")
        return
    tg = _TelegramAdapter(
        token=TELEGRAM_TOKEN,
        chat_id=TELEGRAM_CHAT_ID,
        retry={"max_times": 3, "backoff_sec": 2},
    )
    ok = await tg.send("Test push: Intel-Hub notifier is working")
    print("send result =", ok)
    await tg.close()

if __name__ == "__main__":
    asyncio.run(main())
