# -*- coding: utf-8 -*-
import sys, os, asyncio, httpx, yaml, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "ops" / "sources.yml"

RSS_HINT_RE = re.compile(r"<(rss|feed|rdf)\b", re.I)

async def check_one(client: httpx.AsyncClient, src: dict):
    if not src.get("enabled", True):
        return (src["id"], "SKIP", "disabled")
    url = src.get("url", "")
    if not (url.startswith("http://") or url.startswith("https://")):
        return (src["id"], "BAD", "missing http(s)://")
    try:
        r = await client.get(url, timeout=10)
    except Exception as e:
        return (src["id"], "ERR", str(e))
    kind = r.headers.get("content-type", "")
    is_rss = ("xml" in kind.lower()) or bool(RSS_HINT_RE.search(r.text[:2000]))
    if r.status_code == 200 and is_rss:
        return (src["id"], "OK", kind or "xml")
    return (src["id"], f"{r.status_code}", kind or "unknown")

async def main():
    with open(SOURCES, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources = data.get("sources", [])
    async with httpx.AsyncClient(headers={"User-Agent":"intel-hub/0.1"}) as client:
        results = [await check_one(client, s) for s in sources]
    # Print summary
    ok = [r for r in results if r[1]=="OK"]
    bad = [r for r in results if r[1]!="OK" and r[1]!="SKIP"]
    skip = [r for r in results if r[1]=="SKIP"]
    print("\n=== OK ===")
    for i,_,k in ok: print(f"{i:20} {k}")
    print("\n=== PROBLEM ===")
    for i,s,k in bad: print(f"{i:20} {s:>4}  {k}")
    print("\n=== SKIPPED ===")
    for i,_,k in skip: print(f"{i:20} {k}")

if __name__ == "__main__":
    asyncio.run(main())