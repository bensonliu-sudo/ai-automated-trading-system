# TODO: Default RSS parser
# TODO: RSS/Atom feed parsing
# TODO: Title, content, and time extraction
# TODO: Author extraction
# TODO: Tag and category handling
# TODO: Automatic encoding detection

import time
import feedparser
import datetime
from typing import List, Dict, Optional


def parse_rss(text: str, source_id: str) -> List[Dict]:
    """
    Parse RSS/Atom content and return a list of raw event dicts

    Args:
        text: RSS/Atom XML text
        source_id: data source ID

    Returns:
        List of event dicts, each containing:
        - headline: title
        - link: URL
        - ts_published: publish time (UTC ms)
        - source_id: data source ID
        - raw: raw data (optional)
    """
    events = []

    try:
        # Parse with feedparser
        feed = feedparser.parse(text)

        # Iterate over all entries
        for entry in feed.get('entries', []):
            event = {}

            # Extract title
            event['headline'] = entry.get('title', '').strip()
            if not event['headline']:
                continue

            # Extract link
            event['link'] = entry.get('link', '').strip()
            if not event['link']:
                continue

            # Extract publish time
            ts_published = None

            # Try published_parsed first
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    dt = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
                    ts_published = int(dt.timestamp() * 1000)
                except:
                    pass

            # Fall back to updated_parsed if published_parsed is missing
            if not ts_published and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                try:
                    dt = datetime.datetime(*entry.updated_parsed[:6], tzinfo=datetime.timezone.utc)
                    ts_published = int(dt.timestamp() * 1000)
                except:
                    pass

            # Fall back to the current time if still missing
            if not ts_published:
                ts_published = int(time.time() * 1000)

            event['ts_published'] = ts_published
            event['source_id'] = source_id

            # Keep raw data for debugging
            event['raw'] = {
                'title': entry.get('title'),
                'link': entry.get('link'),
                'published': entry.get('published'),
                'updated': entry.get('updated'),
                'summary': entry.get('summary', '')[:200]  # keep only the first 200 characters
            }

            events.append(event)

    except Exception as e:
        print(f"[rss_parser] parse error source_id={source_id}: {e}")

    return events