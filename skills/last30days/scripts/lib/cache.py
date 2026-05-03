"""On-disk response cache for paid API endpoints.

Key shape: namespace/sha1(key_string).json
Stored:    {"cached_at": <unix_int>, "value": <json-serializable>}
TTL:       enforced on read; expired entries are deleted lazily.
Bypass:    set LAST30DAYS_REFRESH=1 (the --refresh flag does this).
Disable:   set LAST30DAYS_NO_CACHE=1 (or run under unittest/pytest, which is
           auto-detected so unit tests do not write to a developer's cache).

Two TTL bands are used by call sites:
  - SEARCH_TTL  (~6h)  — keyword/profile/hashtag listings; freshness matters.
  - ENRICH_TTL  (~7d)  — per-URL transcripts and comments; rarely change once
                         a video/post has been live for a few hours.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Default TTL bands. Call sites pass ttl_seconds explicitly so each endpoint
# can pick its own band; these constants are the canonical defaults.
SEARCH_TTL = 6 * 60 * 60       # 6 hours: same-day re-runs are free.
ENRICH_TTL = 7 * 24 * 60 * 60  # 7 days: covers daily-cron windows on a topic.

_DEFAULT_ROOT = Path.home() / ".last30days" / "cache"


def _root() -> Path:
    override = os.environ.get("LAST30DAYS_CACHE_DIR")
    return Path(override) if override else _DEFAULT_ROOT


_stats = {"hits": 0, "misses": 0, "stores": 0, "bypass": 0}


def stats() -> dict[str, int]:
    return dict(_stats)


def is_disabled() -> bool:
    """Return True when the cache should not be touched at all.

    Auto-disables under test runners so unit tests do not write into the
    developer's cache directory or read stale fixtures from prior runs.
    """
    if os.environ.get("LAST30DAYS_NO_CACHE") == "1":
        return True
    if "unittest" in sys.modules or "pytest" in sys.modules:
        return True
    return False


def is_refresh_mode() -> bool:
    """Return True when callers should bypass the cache for this run.

    Lookups still report a "bypass" event (not a miss) so callers can tell
    a forced miss from a stale-or-absent miss.
    """
    return os.environ.get("LAST30DAYS_REFRESH") == "1"


def _hash_key(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _path_for(namespace: str, key: str) -> Path:
    return _root() / namespace / f"{_hash_key(key)}.json"


def lookup(namespace: str, key: str, ttl_seconds: int) -> Optional[Any]:
    """Return cached value if present and within TTL; else None.

    None return means the caller should perform the live fetch and may then
    call store() with the result. Lookup never raises.
    """
    if is_disabled():
        return None
    if is_refresh_mode():
        _stats["bypass"] += 1
        return None
    path = _path_for(namespace, key)
    if not path.exists():
        _stats["misses"] += 1
        return None
    try:
        with path.open() as fh:
            entry = json.load(fh)
    except (OSError, json.JSONDecodeError):
        _stats["misses"] += 1
        return None
    cached_at = int(entry.get("cached_at", 0))
    age = int(time.time()) - cached_at
    if age >= ttl_seconds:
        # Lazy eviction so the cache directory does not grow forever.
        try:
            path.unlink()
        except OSError:
            pass
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    return entry.get("value")


def store(namespace: str, key: str, value: Any) -> None:
    """Persist value under namespace/key. Failures are swallowed.

    Cache writes must never break the pipeline, so any IO/serialization
    error is logged at most once per process via stats().
    """
    if is_disabled() or is_refresh_mode():
        return
    path = _path_for(namespace, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"cached_at": int(time.time()), "value": value}
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as fh:
            json.dump(entry, fh)
        tmp.replace(path)
        _stats["stores"] += 1
    except (OSError, TypeError, ValueError):
        pass
