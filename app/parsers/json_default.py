# TODO: Default JSON parser template
# TODO: Generic JSON structure parsing
# TODO: Field mapping config
# TODO: Nested data extraction
# TODO: Array handling
# TODO: Data type conversion

import time
from typing import List, Dict, Union


def parse_json(obj: Union[Dict, List], source_id: str) -> List[Dict]:
    """
    JSON parser template - example mapping; adapt to the specific API

    Example of a typical API response format:
    {
        "items": [
            {
                "title": "News headline",
                "url": "https://example.com/news/123",
                "timestamp": 1640995200000,  # UTC ms, or
                "time": "2022-01-01T00:00:00Z"  # ISO format
            }
        ]
    }

    Usage:
    1. Adjust the field mapping logic below
    2. Adjust the timestamp parsing
    3. Handle nested structures

    Args:
        obj: parsed JSON object (dict or list)
        source_id: data source ID

    Returns:
        List of event dicts
    """
    events = []

    try:
        # Case 1: response is {"items": [...]}
        if isinstance(obj, dict) and 'items' in obj:
            items = obj['items']
        # Case 2: response is a bare array
        elif isinstance(obj, list):
            items = obj
        # Case 3: response is {"data": [...]}
        elif isinstance(obj, dict) and 'data' in obj:
            items = obj['data']
        else:
            # TODO: adjust to the actual API format
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue

            event = {}

            # Extract headline - adjust to the API field names
            # Common field names: title, headline, subject, name
            event['headline'] = item.get('title') or item.get('headline') or item.get('subject', '')
            if not event['headline']:
                continue

            # Extract link - adjust to the API field names
            # Common field names: url, link, href, permalink
            event['link'] = item.get('url') or item.get('link') or item.get('href', '')
            if not event['link']:
                continue

            # Extract timestamp - adjust to the API time format
            ts_published = None

            # Option 1: millisecond timestamp
            if 'timestamp' in item:
                ts_published = int(item['timestamp'])

            # Option 2: second timestamp
            elif 'time' in item and isinstance(item['time'], (int, float)):
                ts_published = int(item['time'] * 1000)

            # Option 3: ISO time string
            elif 'time' in item and isinstance(item['time'], str):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(item['time'].replace('Z', '+00:00'))
                    ts_published = int(dt.timestamp() * 1000)
                except:
                    pass

            # Fall back to the current time if none found
            if not ts_published:
                ts_published = int(time.time() * 1000)

            event['ts_published'] = ts_published
            event['source_id'] = source_id

            # Keep the raw data
            event['raw'] = item

            events.append(event)

    except Exception as e:
        print(f"[json_parser] parse error source_id={source_id}: {e}")

    return events