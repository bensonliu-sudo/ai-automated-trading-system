
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml
import httpx
import feedparser


def _now_ms() -> int:
    return int(time.time() * 1000)

_CLIENT: Optional[httpx.AsyncClient] = None

def _ensure_client() -> httpx.AsyncClient:
    """Reuse a single global httpx AsyncClient to avoid frequent reconnects."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "intel-hub/1.0"})
    return _CLIENT

def normalize_link(url: Optional[str]) -> Optional[str]:
    """
    Normalize a link: strip tracking params such as utm_*, ref/ref_src, and drop the fragment.
    Makes "same article, different URL" easier to recognize as one item.
    """
    if not url:
        return url
    try:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
        u = urlparse(url)
        qs = [
            (k, v)
            for (k, v) in parse_qsl(u.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"ref", "ref_src"}
        ]
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(qs, doseq=True), ""))
    except Exception:
        return url

def _published_ts(entry: Any) -> int:
    """
    Get the publish time from a feedparser entry; fall back to now.
    """
    try:
        if getattr(entry, "published_parsed", None):
            ts = time.mktime(entry.published_parsed)
            return int(ts * 1000)
        if getattr(entry, "updated_parsed", None):
            ts = time.mktime(entry.updated_parsed)
            return int(ts * 1000)
    except Exception:
        pass
    return _now_ms()

# -------------------- Single source: RSS polling --------------------

async def _poll_rss(src: dict, queue: "asyncio.Queue"):
    """
    Poll an RSS source and put parsed entries into q_raw.
    The existing main flow goes q_raw -> scoring -> q_scored -> notifier push.
    """
    url = src.get("url", "")
    interval = int(src.get("interval_sec", 60))
    source_id = src.get("id", "")

    print(f"[collector] RSS started {source_id} every {interval}s")

    client = _ensure_client()
    seen: set[str] = set()  # runtime dedupe (avoid duplicates within a round)

    while True:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[rss] {source_id} failed to respond status={resp.status_code}")
                await asyncio.sleep(min(interval, 30))
                continue

            feed = feedparser.parse(resp.text)

            # Cap the batch size to avoid jitter from very long lists
            for entry in feed.entries[:20]:
                # Title and link
                headline = entry.get("title") or entry.get("summary") or ""
                link_raw = entry.get("link") or entry.get("id") or ""
                link = normalize_link(link_raw)

                # Build a stable uid (prefer link, else title+published)
                base_uid = link or (headline + str(_published_ts(entry)))
                uid = hashlib.sha1(base_uid.encode("utf-8")).hexdigest()

                if uid in seen:
                    continue
                seen.add(uid)

                ts_pub = _published_ts(entry)
                now = _now_ms()

                # Aligned with the project's Event fields (main flow refines in models/scorer/notifier)
                ev = {
                    "id": uid,
                    "headline": headline,
                    "link": link,
                    "ts_published": ts_pub,
                    "ts_detected": now,       # convert later if your model uses ts_detected_utc/ms
                    "source_id": source_id,
                    "raw": entry,
                }

                await queue.put(ev)
                print(f"[rss] {source_id} catch {headline[:60]}")

            # Sleep after a successful round
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            print(f"[rss] {source_id} task cancelled")
            return
        except Exception as e:
            print(f"[rss] {source_id} error: {e!r}")
            # Back off on error to avoid flooding the log
            await asyncio.sleep(min(interval, 60))

# -------------------- Scheduler: read sources.yml and start tasks --------------------

async def run_collectors(queue: "asyncio.Queue") -> List[asyncio.Task]:
    """
    Read ops/sources.yml and start the collector task for each type.
    Only rss is implemented; other types remain placeholders (consistent with the existing structure).
    """
    tasks: List[asyncio.Task] = []

    root = Path(__file__).resolve().parents[1]
    sources: List[Dict[str, Any]] = []

    # sources.yml
    try:
        with open(root / "ops" / "sources.yml", "r", encoding="utf-8") as f:
            sources = (yaml.safe_load(f) or {}).get("sources", [])
    except FileNotFoundError:
        print("[collector] missing ops/sources.yml, skipping")
        sources = []

    # universe.yml (if a watchlist is needed, use it in other collectors)
    try:
        with open(root / "ops" / "universe.yml", "r", encoding="utf-8") as f:
            uni = yaml.safe_load(f) or {}
        watchlist = uni.get("clk_map", {}) or uni.get("ck_map", {}) or {}
    except FileNotFoundError:
        watchlist = {}

    for src in sources:
        if not src.get("enabled", True):
            continue
        t = (src.get("type", "") or "").strip().lower()

        if t == "rss":
            tasks.append(asyncio.create_task(_poll_rss(src, queue)))
        elif t == "api":
            # Placeholder: add _poll_api here if available
            print(f"[collector] unrealized type: api ({src.get('id')}), skipping")
        elif t == "dummy":
            print(f"[collector] unrealized type: dummy ({src.get('id')}), skipping")
        elif t == "edgar_submissions":
            print(f"[collector] unrealized type: edgar_submissions ({src.get('id')}), skipping")
        else:
            print(f"[collector] unknown type: {t} ({src})")

    print(f"[collector] has started {len(tasks)} tasks")
    return tasks