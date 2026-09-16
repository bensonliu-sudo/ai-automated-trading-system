# TODO: keyword classification and scoring module
# TODO: keyword matching engine
# TODO: multi-tier scoring logic
# TODO: topic classification
# TODO: score weight calculation
# TODO: historical data analysis

import asyncio
import hashlib
import time
import yaml
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import aiosqlite

from app.models import Event
from app.storage import insert_event, exists_recent_thread
from app.utils import compile_english_stem, now_ms, norm_text_for_match


class ScorerConfig:
    """Scorer configuration with hot reload support"""

    def __init__(self):
        self.last_reload = 0
        self.reload_interval = 30  # hot reload every 30 seconds

        # Config data
        self.config = {}
        self.keywords = {}
        self.topics = {}
        self.universe = {}

        # Cache of compiled regex patterns
        self.english_patterns = {}

        self._load_all_configs()

    def _load_all_configs(self):
        """Load all config files"""
        try:
            root_path = Path(__file__).parent.parent / "ops"

            # Load config.yml
            with open(root_path / "config.yml", 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}

            # Load keywords.yml
            with open(root_path / "keywords.yml", 'r', encoding='utf-8') as f:
                self.keywords = yaml.safe_load(f) or {}

            # Load topics.yml
            with open(root_path / "topics.yml", 'r', encoding='utf-8') as f:
                self.topics = yaml.safe_load(f) or {}

            # Load universe.yml
            with open(root_path / "universe.yml", 'r', encoding='utf-8') as f:
                self.universe = yaml.safe_load(f) or {}

            # Compile English keyword regexes
            self._compile_english_patterns()

            self.last_reload = time.time()
            print("[scorer] config loaded")

        except Exception as e:
            print(f"[scorer] config load failed: {e}")

    def _compile_english_patterns(self):
        """Compile regex patterns for English keywords"""
        self.english_patterns.clear()

        # Compile tier1 keywords
        tier1 = self.keywords.get('tiers', {}).get('tier1', [])
        for keyword in tier1:
            if keyword.isascii() and keyword.islower():
                self.english_patterns[keyword] = compile_english_stem(keyword)

        # Compile tier2 keywords
        tier2 = self.keywords.get('tiers', {}).get('tier2', [])
        for keyword in tier2:
            if keyword.isascii() and keyword.islower():
                self.english_patterns[keyword] = compile_english_stem(keyword)

        # Compile negative keywords
        negatives = self.keywords.get('negatives', [])
        for keyword in negatives:
            if keyword.isascii() and keyword.islower():
                self.english_patterns[keyword] = compile_english_stem(keyword)

    def should_reload(self) -> bool:
        """Check whether the config needs reloading"""
        return time.time() - self.last_reload > self.reload_interval

    def reload_if_needed(self):
        """Reload the config if needed"""
        if self.should_reload():
            self._load_all_configs()


# Global config instance
_scorer_config = ScorerConfig()


def _check_blacklist(headline: str, source_id: str) -> bool:
    """
    Check the blacklist

    Returns:
        True: should be discarded
        False: safe to continue processing
    """
    # Check source blacklist
    source_blacklist = _scorer_config.keywords.get('source_blacklist', [])
    if source_id in source_blacklist:
        print(f"[scorer] discarding blacklisted source: {source_id}")
        return True

    # Check keyword blacklist
    keyword_blacklist = _scorer_config.keywords.get('keyword_blacklist', [])
    lower_text, _ = norm_text_for_match(headline)

    for blackword in keyword_blacklist:
        if isinstance(blackword, str):
            if blackword.isascii():
                # English blacklist word
                if blackword.lower() in lower_text:
                    print(f"[scorer] discarding headline with blacklisted word: {blackword}")
                    return True
            else:
                # Chinese blacklist word
                if blackword in headline:
                    print(f"[scorer] discarding headline with blacklisted word: {blackword}")
                    return True

    return False


def _extract_symbols(headline: str) -> str:
    """
    Extract ticker symbols from the headline

    Returns:
        Semicolon-separated string of ticker symbols
    """
    watchlist = _scorer_config.universe.get('watchlist', [])
    found_symbols = []

    for symbol in watchlist:
        if isinstance(symbol, str) and symbol.upper() in headline.upper():
            found_symbols.append(symbol.upper())

    return ';'.join(found_symbols)


def _match_keywords(headline: str) -> Tuple[List[str], List[str], int, int, int]:
    """
    Match keywords and count hits

    Returns:
        (tier1_keywords, tier2_keywords, tier1_hits, tier2_hits, negative_hits)
    """
    lower_text, original_text = norm_text_for_match(headline)

    tier1_keywords = []
    tier2_keywords = []
    tier1_hits = 0
    tier2_hits = 0
    negative_hits = 0

    # Match tier1 keywords
    tier1_list = _scorer_config.keywords.get('tiers', {}).get('tier1', [])
    for keyword in tier1_list:
        if isinstance(keyword, str):
            if keyword.isascii() and keyword.islower():
                # English keyword: regex match
                pattern = _scorer_config.english_patterns.get(keyword)
                if pattern and pattern.search(lower_text):
                    tier1_keywords.append(keyword)
                    tier1_hits += 1
            else:
                # Chinese keyword: direct substring match
                if keyword in original_text:
                    tier1_keywords.append(keyword)
                    tier1_hits += 1

    # Match tier2 keywords
    tier2_list = _scorer_config.keywords.get('tiers', {}).get('tier2', [])
    for keyword in tier2_list:
        if isinstance(keyword, str):
            if keyword.isascii() and keyword.islower():
                # English keyword: regex match
                pattern = _scorer_config.english_patterns.get(keyword)
                if pattern and pattern.search(lower_text):
                    tier2_keywords.append(keyword)
                    tier2_hits += 1
            else:
                # Chinese keyword: direct substring match
                if keyword in original_text:
                    tier2_keywords.append(keyword)
                    tier2_hits += 1

    # Match negative keywords
    negatives = _scorer_config.keywords.get('negatives', [])
    for keyword in negatives:
        if isinstance(keyword, str):
            if keyword.isascii() and keyword.islower():
                # English keyword: regex match
                pattern = _scorer_config.english_patterns.get(keyword)
                if pattern and pattern.search(lower_text):
                    negative_hits += 1
            else:
                # Chinese keyword: direct substring match
                if keyword in original_text:
                    negative_hits += 1

    return tier1_keywords, tier2_keywords, tier1_hits, tier2_hits, negative_hits


def _match_topics(headline: str) -> List[str]:
    """
    Match topic tags

    Returns:
        List of matched hashtags
    """
    matched_hashtags = []
    topics = _scorer_config.topics.get('topics', {})

    for topic_name, topic_config in topics.items():
        tags = topic_config.get('tags', [])
        hashtag = topic_config.get('hashtag', '')

        for tag in tags:
            if isinstance(tag, str):
                if tag in headline:
                    if hashtag and hashtag not in matched_hashtags:
                        matched_hashtags.append(hashtag)
                    break

    return matched_hashtags


def _calculate_score(tier1_hits: int, tier2_hits: int, negative_hits: int,
                    has_watchlist_symbol: bool) -> float:
    """
    Calculate the event score

    Returns:
        Computed score
    """
    weights = _scorer_config.keywords.get('weights', {})

    score = weights.get('source_rss_base', 20)
    score += tier1_hits * weights.get('tier1', 50)
    score += tier2_hits * weights.get('tier2', 25)
    score += negative_hits * weights.get('negative', -30)

    if has_watchlist_symbol:
        score += weights.get('watchlist_bonus', 10)

    return float(score)


def _create_event_from_raw(raw_event: Dict[str, Any]) -> Event:
    """
    Convert a raw event dict into an Event object

    Args:
        raw_event: raw event data

    Returns:
        Event object
    """
    headline = raw_event.get('headline', '')
    link = raw_event.get('link', '')
    source_id = raw_event.get('source_id', '')
    ts_published = raw_event.get('ts_published', now_ms())

    # Generate event ID
    event_id = hashlib.sha1(f"{source_id}|{link}".encode()).hexdigest()

    # Extract ticker symbols
    symbols = _extract_symbols(headline)

    # Match keywords
    tier1_keywords, tier2_keywords, tier1_hits, tier2_hits, negative_hits = _match_keywords(headline)

    # Match topics
    hashtags = _match_topics(headline)

    # Calculate score
    has_watchlist_symbol = bool(symbols)
    score = _calculate_score(tier1_hits, tier2_hits, negative_hits, has_watchlist_symbol)

    # Build categories
    all_keywords = tier1_keywords + tier2_keywords
    categories = ';'.join(all_keywords) if all_keywords else 'general'

    # Build tags
    tags = ';'.join(hashtags) if hashtags else ''

    # Build thread_key
    primary_symbol = symbols.split(';')[0] if symbols else source_id
    primary_category = tier1_keywords[0] if tier1_keywords else (tier2_keywords[0] if tier2_keywords else 'general')
    thread_key = f"{primary_symbol}|{primary_category}"

    # Calculate expiry time
    retention_hours = _scorer_config.config.get('retention_hours', 48)
    ts_detected = now_ms()
    expires_at = ts_detected + retention_hours * 3600 * 1000

    return Event(
        id=event_id,
        ts_detected_utc=ts_detected,
        ts_published_utc=ts_published,
        headline=headline,
        source=source_id,
        link=link,
        market="us",
        symbols=symbols,
        categories=categories,
        tags=tags,
        score=score,
        pushed=0,
        expires_at_utc=expires_at,
        thread_key=thread_key
    )


async def _should_notify(event: Event, db: aiosqlite.Connection) -> bool:
    """
    Decide whether a notification should be pushed

    Args:
        event: event object
        db: database connection

    Returns:
        Whether to push
    """
    # Check score threshold
    important_threshold = _scorer_config.config.get('important_threshold', 70)
    if event.score < important_threshold:
        return False

    # Check dedupe throttling
    dedupe_minutes = _scorer_config.config.get('dedupe_minutes', 15)

    # Check for a recent event on the same thread
    if await exists_recent_thread(db, event.thread_key, dedupe_minutes):
        # Check whether this is a higher-score escalation push
        critical_threshold = _scorer_config.config.get('critical_threshold', 85)
        if event.score >= critical_threshold:
            print(f"[scorer] escalation push: {event.headline[:50]}... (score={event.score})")
            return True
        else:
            print(f"[scorer] throttled, skipping: {event.headline[:50]}... (score={event.score})")
            return False

    return True


async def run_scorer(q_in: asyncio.Queue, q_out: asyncio.Queue, db: aiosqlite.Connection) -> None:
    """
    Read raw event dicts from q_in -> score/tag/dedupe -> store; if the important/critical threshold is reached, put into q_out for the notifier

    Args:
        q_in: input queue of raw event dicts
        q_out: output queue for the notifier
        db: database connection
    """
    print("[scorer] starting scorer")

    while True:
        try:
            # Hot reload config
            _scorer_config.reload_if_needed()

            # Get raw event from queue
            raw_event = await q_in.get()

            # Check expiry
            retention_hours = _scorer_config.config.get('retention_hours', 48)
            now = now_ms()
            ts_published = raw_event.get('ts_published', now)

            if now - ts_published > retention_hours * 3600 * 1000:
                print(f"[scorer] discard expired event: {raw_event.get('headline', '')[:50]}...")
                continue

            # Check blacklist
            headline = raw_event.get('headline', '')
            source_id = raw_event.get('source_id', '')

            if _check_blacklist(headline, source_id):
                continue

            # Convert to Event object
            event = _create_event_from_raw(raw_event)

            # Store in database
            success = await insert_event(db, event)
            if not success:
                print(f"[scorer] fail to storage: {event.headline[:50]}...")
                continue

            print(f"[scorer] saved to database: {event.headline[:50]}... (score={event.score})")

            # Decide whether to push
            if await _should_notify(event, db):
                await q_out.put(event)
                print(f"[scorer] push: {event.headline[:50]}...")

        except asyncio.CancelledError:
            print("[scorer] cancelled")
            break
        except Exception as e:
            print(f"[scorer] failed: {e}")


def score_headline_for_test(headline: str) -> Tuple[str, str, float]:
    """
    Used by tests/test_all.py: takes a headline, returns (categories_str, tags_str, score)

    Args:
        headline: headline text

    Returns:
        (categories string, tags string, score)
    """
    # Ensure config is loaded
    _scorer_config.reload_if_needed()

    # Extract ticker symbols
    symbols = _extract_symbols(headline)

    # Match keywords
    tier1_keywords, tier2_keywords, tier1_hits, tier2_hits, negative_hits = _match_keywords(headline)

    # Match topics
    hashtags = _match_topics(headline)

    # Calculate score
    has_watchlist_symbol = bool(symbols)
    score = _calculate_score(tier1_hits, tier2_hits, negative_hits, has_watchlist_symbol)

    # Build categories
    all_keywords = tier1_keywords + tier2_keywords
    categories = ';'.join(all_keywords) if all_keywords else 'general'

    # Build tags
    tags = ';'.join(hashtags) if hashtags else ''

    return categories, tags, score

