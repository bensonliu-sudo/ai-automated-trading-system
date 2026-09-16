# TODO: Utility module
# TODO: Timezone conversion helpers
# TODO: Config hot-reload mechanism
# TODO: Translation API placeholder interface
# TODO: English inflection matching (plural, tense)
# TODO: Logging helpers
# TODO: General helper functions

import re
import time
from typing import Tuple


def compile_english_stem(stem: str) -> re.Pattern:
    """
    Compile a regex for an English stem that matches inflected forms

    Args:
        stem: English word stem (lowercase)

    Returns:
        Compiled regex matching the stem and its inflections
    """
    # Build the pattern: \bstem(s|es|ed|ing)?\b
    pattern = rf'\b{re.escape(stem)}(s|es|ed|ing)?\b'
    return re.compile(pattern, re.IGNORECASE)


def now_ms() -> int:
    """
    Get the current UTC timestamp in milliseconds

    Returns:
        Current time as a millisecond timestamp
    """
    return int(time.time() * 1000)


def norm_text_for_match(s: str) -> Tuple[str, str]:
    lower = s.lower()
    # Prevent ray-ban from matching ban
    lower = lower.replace("ray-ban", "rayban")
    return lower, s