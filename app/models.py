# TODO: Define data models
# TODO: Source model - data source config
# TODO: Event model - collected events
# TODO: Score model - event scoring
# TODO: Notification model - push records

# -*- coding: utf-8 -*-
"""
models.py
Defines the event data model. Field names must match tests/test_all.py,
otherwise constructing Event in Step 2 will fail.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class Event:
    # Primary key ID (recommended: hash of URL+time, or UUID; string type here)
    id: str

    # Detection time and publish time (UTC, milliseconds)
    ts_detected_utc: int
    ts_published_utc: Optional[int]  # may be None

    # Headline, source name, original link
    headline: str
    source: str
    link: str

    # Market tag: e.g. "us" / "crypto"
    market: str

    # Multi-value fields stored as semicolon-separated strings: e.g. "NVDA;AMD"
    symbols: str
    categories: str  # e.g. "contract;ai upgrade"
    tags: str        # e.g. "#AI;#Semis"

    # Score and push status
    score: float
    pushed: int      # 0/1

    # Expiry time (UTC ms), used for cleanup
    expires_at_utc: int

    # Thread key: used for throttling, e.g. "NVDA|contract"
    thread_key: str