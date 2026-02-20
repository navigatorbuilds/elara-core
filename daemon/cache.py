# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Cortical Layer 0 — REFLEX cache.

TTL-based in-memory cache with event-driven invalidation.
Zero-I/O for common reads: mood, presence stats, imprints, context.

Design:
  - Simple dict {key: (value, expires_at)} + threading.Lock
  - Lazy population (cache on first miss)
  - Event subscriptions invalidate stale entries automatically
  - ~15 keys total, no size eviction needed
  - Falls through to normal I/O on miss (graceful degradation)
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("elara.cache")

# Cache entry: (value, expires_at_monotonic)
CacheEntry = Tuple[Any, float]


class CorticalCache:
    """
    Layer 0 reflex cache — hot reads with TTL expiry and event invalidation.

    Thread-safe via threading.Lock. All operations are O(1).
    """

    def __init__(self):
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None on miss or expiry."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        """Store a value with TTL in seconds."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, *keys: str) -> int:
        """Invalidate one or more cache keys. Returns count of keys actually removed."""
        removed = 0
        with self._lock:
            for key in keys:
                if key in self._store:
                    del self._store[key]
                    removed += 1
            self._invalidations += removed
        if removed:
            logger.debug("Cache invalidated: %s (%d removed)", keys, removed)
        return removed

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
        if count:
            logger.debug("Cache cleared (%d entries)", count)

    def stats(self) -> Dict[str, Any]:
        """Cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
                "invalidations": self._invalidations,
            }

    def get_or_compute(
        self, key: str, ttl: float, compute_fn: Callable[[], Any]
    ) -> Any:
        """Get from cache, or compute + cache on miss. Thread-safe."""
        value = self.get(key)
        if value is not None:
            return value
        # Compute outside lock to avoid blocking other cache ops
        result = compute_fn()
        self.set(key, result, ttl)
        return result


# ---------------------------------------------------------------------------
# Cache key constants and TTLs
# ---------------------------------------------------------------------------

class CacheKeys:
    """Standard cache keys and their TTLs."""
    MOOD_STATE = "mood_state"
    IMPRINTS = "imprints"
    PRESENCE_STATS = "presence_stats"
    MEMORY_COUNT = "memory_count"
    CONTEXT_DATA = "context_data"
    GOAL_LIST = "goal_list"
    CORRECTION_INDEX = "correction_index"
    LLM_AVAILABILITY = "llm_availability"
    DREAM_STATUS = "dream_status"


# TTLs in seconds
CACHE_TTLS: Dict[str, float] = {
    CacheKeys.MOOD_STATE: 5.0,
    CacheKeys.IMPRINTS: 10.0,
    CacheKeys.PRESENCE_STATS: 30.0,
    CacheKeys.MEMORY_COUNT: 60.0,
    CacheKeys.CONTEXT_DATA: 30.0,
    CacheKeys.GOAL_LIST: 120.0,
    CacheKeys.CORRECTION_INDEX: 120.0,
    CacheKeys.LLM_AVAILABILITY: 60.0,
    CacheKeys.DREAM_STATUS: 300.0,
}

# Map events → cache keys to invalidate
# Imported lazily to avoid circular imports
_EVENT_INVALIDATION_MAP: Dict[str, List[str]] = {}


def _build_invalidation_map() -> Dict[str, List[str]]:
    """Build event→cache key mapping. Called once at init."""
    from daemon.events import Events
    return {
        Events.MOOD_CHANGED: [CacheKeys.MOOD_STATE],
        Events.MOOD_SET: [CacheKeys.MOOD_STATE],
        Events.IMPRINT_CREATED: [CacheKeys.IMPRINTS, CacheKeys.MOOD_STATE],
        Events.IMPRINT_DECAYED: [CacheKeys.IMPRINTS],
        Events.SESSION_STARTED: [CacheKeys.PRESENCE_STATS],
        Events.SESSION_ENDED: [CacheKeys.PRESENCE_STATS],
        Events.MEMORY_SAVED: [CacheKeys.MEMORY_COUNT],
        Events.MEMORY_CONSOLIDATED: [CacheKeys.MEMORY_COUNT],
        Events.GOAL_ADDED: [CacheKeys.GOAL_LIST],
        Events.GOAL_UPDATED: [CacheKeys.GOAL_LIST],
        Events.CORRECTION_ADDED: [CacheKeys.CORRECTION_INDEX],
        Events.LLM_UNAVAILABLE: [CacheKeys.LLM_AVAILABILITY],
        Events.DREAM_COMPLETED: [CacheKeys.DREAM_STATUS],
    }


def setup_cache_invalidation(cache_instance: CorticalCache) -> None:
    """Subscribe to events that should invalidate cache entries."""
    from daemon.events import bus

    global _EVENT_INVALIDATION_MAP
    _EVENT_INVALIDATION_MAP = _build_invalidation_map()

    def _on_invalidating_event(event):
        keys = _EVENT_INVALIDATION_MAP.get(event.type, [])
        if keys:
            cache_instance.invalidate(*keys)

    for event_type in _EVENT_INVALIDATION_MAP:
        bus.on(event_type, _on_invalidating_event, priority=100, source="cache")

    logger.info(
        "Cache invalidation wired: %d events → %d cache keys",
        len(_EVENT_INVALIDATION_MAP),
        sum(len(v) for v in _EVENT_INVALIDATION_MAP.values()),
    )


# ---------------------------------------------------------------------------
# SINGLETON — the global cortical cache
# ---------------------------------------------------------------------------

cache = CorticalCache()
