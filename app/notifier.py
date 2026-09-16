
"""
app/notifier.py
Notifier module: consumes high-priority events from the scorer and sends them to Telegram (or falls back to stdout)
- Reads ops/config.yml (30s hot reload)
- Supports quiet hours (do not disturb)
- Dedupe/throttle: per thread_key, only push higher scores within the window; optional batch merging
- Simple English-to-Chinese placeholder translation (can be replaced with a real translation API later)
"""

from __future__ import annotations
import os
import time
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Dict, Tuple

import httpx
import yaml

from app.models import Event
# from app.main import load_cfg


# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _load_cfg() -> dict:
    """Read ops/config.yml; return defaults if missing"""
    root = Path(__file__).resolve().parents[1]
    p = root / "ops" / "config.yml"
    if not p.exists():
        # Minimal default config
        return {
            "notifier": {
                "channel": "telegram",
                "translate_to_zh": True,
                "quiet_hours": "00:00-00:00",
                "batch_window_sec": 0,
                "dedupe_minutes": 30,
                "retry": {"max_times": 3, "backoff_sec": 2},
            },
            "important_threshold": 70,
            "critical_threshold": 90,
            "display_timezone": "America/New_York",
        }
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Fill in defaults
    data.setdefault("notifier", {})
    n = data["notifier"]
    n.setdefault("channel", "telegram")
    n.setdefault("translate_to_zh", True)
    n.setdefault("quiet_hours", "00:00-00:00")
    n.setdefault("batch_window_sec", 0)
    n.setdefault("dedupe_minutes", 30)
    n.setdefault("retry", {"max_times": 3, "backoff_sec": 2})
    data.setdefault("important_threshold", 70)
    data.setdefault("critical_threshold", 90)
    data.setdefault("display_timezone", "America/New_York")
    return data


def _parse_hhmm(s: str) -> int:
    """'HH:MM' -> minutes"""
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)


def _in_quiet_hours(rng: str) -> bool:
    """
    quiet_hours: 'HH:MM-HH:MM' in local time
    Equal start and end means quiet hours are disabled (zero length)
    Ranges crossing midnight (e.g. 23:00-07:30) are handled correctly
    """
    if not rng or "-" not in rng:
        return False
    try:
        start, end = rng.split("-")
        start_m = _parse_hhmm(start)
        end_m = _parse_hhmm(end)
        now_local = time.localtime()
        now_m = now_local.tm_hour * 60 + now_local.tm_min
        if start_m == end_m:
            return False  # disabled
        if start_m < end_m:
            return start_m <= now_m < end_m
        # Crosses midnight
        return now_m >= start_m or now_m < end_m
    except Exception:
        return False


def _truncate(s: str, limit: int = 3500) -> str:
    if s is None:
        return ""
    return s if len(s) <= limit else s[:limit - 3] + "..."


# Very simple term substitution table (placeholder)
_EN2ZH = {
    "invest": "投资",
    "investment": "投资",
    "contract": "合同",
    "order": "订单",
    "partnership": "战略合作",
    "acquire": "收购",
    "acquisition": "收购",
    "buyback": "回购",
    "guidance": "指引",
    "appoint": "任命",
    "resign": "辞任",
    "management change": "管理层变更",
    "milestone": "里程碑",
    "breakthrough": "技术突破",
    "upgrade": "升级",
    "rwa": "RWA",
    "spot etf": "现货ETF",
    "ipo": "IPO",
}


def _translate_to_zh(text: str) -> str:
    """Minimal placeholder translation: substitute a few terms, return the rest unchanged"""
    if not text:
        return text
    low = text.lower()
    for k, v in _EN2ZH.items():
        if k in low:
            low = low.replace(k, v)
    # Simple handling of the Ray-Ban ambiguity
    low = low.replace("ray-ban", "RayBan")
    return low


# ------------------------------------------------------------
# Channel adapters
# ------------------------------------------------------------

# ===== notifier.py key changes =====
import os, random
import httpx

class _TelegramAdapter:
    def __init__(self, token: str, chat_id: str, retry: dict[int, int]):
        self._token = token
        self._chat_id = chat_id
        self._retry = retry
        self._client: Optional[httpx.AsyncClient] = None

    def _client_get(self) -> httpx.AsyncClient:
        # Reuse client, read system proxy; shorter timeouts, HTTP/2 is more stable; keep connection pool
        if self._client is None:
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=30.0)
            proxies = None
            # Allow passing a proxy via environment variables or config (optional)
            # e.g. in main, put notifier_cfg['proxies'] into environment variables
            if os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY"):
                proxies = {"all://": os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")}
            self._client = httpx.AsyncClient(
                timeout=timeout,
                http2=True,
                trust_env=True,   # <== read system proxy/CERT
                proxies=proxies
            )
        return self._client

    async def send(self, text: str) -> bool:
        """
        Send to Telegram; respect 429/5xx; print a short message only on final failure.
        """
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        max_times = int(self._retry.get("max_times", 3))
        backoff  = int(self._retry.get("backoff_sec", 2))

        last_err = None

        for attempt in range(1, max_times + 1):
            try:
                r = await self._client_get().post(url, data=payload)
                # Telegram commonly returns JSON even on non-200
                data = None
                try:
                    data = r.json()
                except Exception:
                    data = None

                if r.status_code == 200 and (data is None or data.get("ok", True) is True):
                    return True

                # 429/5xx: retryable
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    retry_after = 0
                    try:
                        j = data or r.json()
                        retry_after = int(j.get("parameters", {}).get("retry_after", 0))
                    except Exception:
                        pass
                    # Exponential backoff + jitter, prefer server-provided retry_after
                    sleep_sec = retry_after or (backoff * (2 ** (attempt - 1)))
                    sleep_sec = min(sleep_sec, 30)  # cap at 30s to avoid waiting too long
                    sleep_sec += random.uniform(0, 0.6)
                    await asyncio.sleep(sleep_sec)
                    continue

                # Other 4xx: fail immediately, log the first 300 chars
                last_err = f"http {r.status_code}: {(r.text or '')[:300]}"
                break

            except Exception as e:
                last_err = repr(e)
                # Network jitter: retry with backoff as well
                sleep_sec = backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.6)
                await asyncio.sleep(min(sleep_sec, 20))
                continue

        # Print only once on final failure
        print(f"[notifier] telegram send failed after {max_times} attempts: {last_err}")
        return False

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class _StdoutAdapter:
    async def send(self, text: str) -> bool:
        print("\n" + text + "\n")
        return True

    async def close(self):
        return


# ------------------------------------------------------------
# Notifier core
# ------------------------------------------------------------

class Notifier:
    def __init__(self, cfg: Optional[dict] = None):
        raw = cfg or load_cfg()

        # ---- Normalize so that self._cfg is the "notifier" sub-config ----
        if "notifier" in raw:
            self._cfg = raw["notifier"]
        else:
            self._cfg = raw

        self._cfg_reload_ms = _now_ms()
        self._cfg_last_mtime = None

        # Sent cache
        self._sent_cache: Dict[str, Tuple[float, int]] = {}
        self._batch_state: Dict[str, dict] = {}

        # Read token/chat_id from environment variables (config may override)
        token = self._cfg.get("token") or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = self._cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        retry = self._cfg.get("retry", 1)

        # ---- Fix: support notify_channels ----
        channels = self._cfg.get("notify_channels") or []
        if "telegram" in channels and token and chat_id:
            self._adapter = _TelegramAdapter(token, chat_id, retry)
            self._channel = "telegram"
        else:
            self._adapter = _StdoutAdapter()
            self._channel = "stdout"
            if "telegram" in channels:
                print("[notifier] TELEGRAM_BOT_TOKEN/CHAT_ID missing, falling back to stdout")

        # Batch window parameter
        self._batch_window_sec = int(self._cfg.get("batch_window_sec", 0))

    async def start(self, q_in: "asyncio.Queue") -> None:
        """Long-running: consume the queue and push according to policy"""
        try:
            while True:
                # Config hot reload (every 30s)
                if _now_ms() - self._cfg_reload_ms > 30 * 1000:
                    self._try_reload_cfg()

                ev: Event = await q_in.get()

                # Quiet hours: print as a "muted" record (no push)
                if _in_quiet_hours(self._cfg.get("quiet_hours", "")):
                    text = self._format_text(ev, muted=True)
                    await self._adapter.send(text)
                    continue

                # Dedupe/throttle
                if self._is_duplicated(ev):
                    continue

                # Batch window
                if self._batch_window_sec > 0 and ev.thread_key:
                    key = ev.thread_key
                    now = _now_ms()
                    st = self._batch_state.get(key)
                    if st is None:
                        self._batch_state[key] = {"t0": now, "best": ev, "n": 1}
                        continue
                    # Update best
                    if ev.score > st["best"].score:
                        st["best"] = ev
                    st["n"] += 1
                    # Push when window expires
                    if now - st["t0"] >= self._batch_window_sec * 1000:
                        text = self._format_text(st["best"], batch_n=st["n"])
                        await self._adapter.send(text)
                        self._mark_sent(st["best"])
                        self._batch_state.pop(key, None)
                    continue

                # Push directly
                ok = await self.push(ev)
                if ok:
                    self._mark_sent(ev)

        except asyncio.CancelledError:
            # Flush the batch window before exiting
            if self._batch_window_sec > 0:
                for key, st in list(self._batch_state.items()):
                    text = self._format_text(st["best"], batch_n=st["n"])
                    await self._adapter.send(text)
                    self._mark_sent(st["best"])
                self._batch_state.clear()
            return

    async def push(self, ev: Event) -> bool:
        """Push a single event (sent directly via the adapter)"""
        text = self._format_text(ev)
        return await self._adapter.send(text)

    # --------------- Internal methods ---------------

    def _is_duplicated(self, ev: Event) -> bool:
        """Within the window, only push higher scores for the same thread_key; window defaults to dedupe_minutes"""
        key = ev.thread_key or ""
        if not key:
            return False
        win_min = int(self._cfg.get("dedupe_minutes", 30))
        now = _now_ms()
        last = self._sent_cache.get(key)
        if last is None:
            return False
        last_score, last_ts = last
        if now - last_ts > win_min * 60 * 1000:
            return False
        # Score not higher than last time => ignore
        if ev.score <= last_score:
            return True
        return False

    def _mark_sent(self, ev: Event) -> None:
        key = ev.thread_key or ""
        if not key:
            return
        self._sent_cache[key] = (float(ev.score or 0.0), _now_ms())

    def _format_text(self, ev: Event, muted: bool = False, batch_n: int = 0) -> str:
        """Unified message format"""
        score = float(ev.score or 0.0)
        important = int(self._cfg.get("important_threshold", 70))
        critical = int(self._cfg.get("critical_threshold", 90))
        level = "🟢Important" if score >= important else "✅Notice"
        if score >= critical:
            level = "🔴Critical"

        # Tags
        tags = (ev.tags or "").strip()
        if tags and not tags.startswith("#"):
            # Support semicolons/commas
            tags = "#" + tags.replace(";", " #").replace(",", " #")

        # Headline + optional Chinese
        headline = ev.headline or ""
        text = f"{level} {tags}\n{headline}"

        if self._cfg.get("translate_to_zh", True):
            zh = _translate_to_zh(headline)
            if zh and zh != headline:
                text += f"\n[ZH] {zh}"

        cats = ev.categories or "-"
        syms = ev.symbols or "-"
        link = ev.link or "-"
        src = getattr(ev, "source", None) or getattr(ev, "source_id", None) or "-"

        ts_pub = ev.ts_published_utc or 0
        ts_det = ev.ts_detected_utc or 0

        if batch_n > 1:
            text += f"\n(merged {batch_n} updates)"

        text += (
            f"\nSource: {src} | Score: {score:.1f}"
            f"\nCats: {cats}"
            f"\nTicker: {syms}"
            f"\nLink: {link}"
            f"\nPublished(UTC): {ts_pub} | Detected: {ts_det}"
        )

        if muted:
            text += "\n(quiet hours – muted)"

        return _truncate(text, 3500)

    def _try_reload_cfg(self) -> None:
        """Hot reload config every 30s (reload if the file mtime changed)"""
        root = Path(__file__).resolve().parents[1]
        p = root / "ops" / "config.yml"
        self._cfg_reload_ms = _now_ms()
        try:
            m = p.stat().st_mtime if p.exists() else None
            if self._cfg_last_mtime is None or m != self._cfg_last_mtime:
                self._cfg = _load_cfg()
                self._cfg_last_mtime = m
                # Refresh batch window config
                self._batch_window_sec = int(self._cfg.get("batch_window_sec", 0))
                # Reload mode: if token/chat was missing at startup, stay on stdout; avoid confusing runtime switches
                print("[notifier] config hot reloaded")
        except Exception as e:
            print(f"[notifier] config hot reload failed: {e}")

    async def close(self):
        if isinstance(self._adapter, _TelegramAdapter):
            await self._adapter.close()