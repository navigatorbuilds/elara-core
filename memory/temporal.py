# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Long-Range Memory — temporal sweep across the full timeline.

Problem: Boot pipeline only surfaces last 7 days of memories. Anything
older is invisible unless a specific semantic query happens to match.
User asks "what did we do 2 months ago?" and gets nothing.

Solution: Query memories and milestones across time windows at boot,
surfacing the most important items from each period. Also surface
"landmark" memories (importance >= 0.9) that should never be forgotten.

Time windows:
  Window 1: 1-2 weeks ago     → top 2 by importance
  Window 2: 2-4 weeks ago     → top 2 by importance
  Window 3: 1-3 months ago    → top 2 by importance
  Window 4: 3+ months ago     → top 1 by importance

Cost: 4-5 ChromaDB queries (~200-300ms total at boot).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("elara.memory.temporal")

# Time windows: (label, start_days_ago, end_days_ago, max_results)
TIME_WINDOWS: List[Tuple[str, int, int, int]] = [
    ("1-2 weeks ago", 7, 14, 2),
    ("2-4 weeks ago", 14, 28, 2),
    ("1-3 months ago", 28, 90, 2),
    ("3+ months ago", 90, 365 * 5, 1),
]

# Minimum importance to surface in temporal sweep
MIN_IMPORTANCE = 0.5

# Landmark threshold — always surface regardless of time
LANDMARK_THRESHOLD = 0.9


def temporal_sweep(
    min_importance: float = MIN_IMPORTANCE,
    include_landmarks: bool = True,
    include_milestones: bool = True,
) -> List[Dict[str, Any]]:
    """
    Sweep memories across time windows, returning the most important
    items from each period.

    Returns list of dicts: {content, date, importance, type, window, source}
    Sorted by date (oldest first) for chronological narrative.
    """
    results = []

    # --- Semantic memories from ChromaDB ---
    try:
        from memory.vector import get_memory
        mem = get_memory()
        if mem.collection:
            for label, start_days, end_days, max_n in TIME_WINDOWS:
                window_results = _query_memories_in_window(
                    mem, start_days, end_days, max_n, min_importance
                )
                for item in window_results:
                    item["window"] = label
                    item["source"] = "memory"
                results.extend(window_results)
    except Exception as e:
        logger.debug("Memory temporal sweep failed: %s", e)

    # --- Milestones from episodic memory ---
    if include_milestones:
        try:
            from memory.episodic import get_episodic
            episodic = get_episodic()
            if episodic.milestones_collection:
                for label, start_days, end_days, max_n in TIME_WINDOWS:
                    window_results = _query_milestones_in_window(
                        episodic, start_days, end_days, max_n, min_importance
                    )
                    for item in window_results:
                        item["window"] = label
                        item["source"] = "milestone"
                    results.extend(window_results)
        except Exception as e:
            logger.debug("Milestone temporal sweep failed: %s", e)

    # --- Landmarks (importance >= 0.9, any time) ---
    if include_landmarks:
        try:
            landmarks = recall_landmarks()
            for item in landmarks:
                item["window"] = "landmark"
                item["source"] = "landmark"
            results.extend(landmarks)
        except Exception as e:
            logger.debug("Landmark sweep failed: %s", e)

    # Deduplicate by content similarity (exact match on first 80 chars)
    seen = set()
    deduped = []
    for r in results:
        key = r.get("content", "")[:80]
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Sort by date (oldest first) for chronological narrative
    deduped.sort(key=lambda x: x.get("date", "9999"))

    return deduped


def recall_landmarks(max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Recall landmark memories (importance >= 0.9).
    These are the "never forget" tier — always surface at boot.
    """
    try:
        from memory.vector import get_memory
        mem = get_memory()
        if not mem.collection:
            return []

        # ChromaDB where filter for high-importance memories
        results = mem.collection.get(
            where={"importance": {"$gte": LANDMARK_THRESHOLD}},
            limit=max_results,
            include=["documents", "metadatas"],
        )

        items = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                items.append({
                    "content": doc,
                    "date": meta.get("date", "unknown"),
                    "importance": meta.get("importance", 1.0),
                    "type": meta.get("type", "unknown"),
                })

        # Sort by importance descending
        items.sort(key=lambda x: -x.get("importance", 0))
        return items

    except Exception as e:
        logger.debug("Landmark recall failed: %s", e)
        return []


def _query_memories_in_window(
    mem, start_days: int, end_days: int, max_n: int, min_importance: float
) -> List[Dict[str, Any]]:
    """Query memories within a time window, sorted by importance."""
    now = datetime.now()
    start_date = (now - timedelta(days=end_days)).strftime("%Y-%m-%d")
    end_date = (now - timedelta(days=start_days)).strftime("%Y-%m-%d")

    try:
        # ChromaDB where filter: date >= start_date AND date <= end_date AND importance >= min
        results = mem.collection.get(
            where={
                "$and": [
                    {"date": {"$gte": start_date}},
                    {"date": {"$lte": end_date}},
                    {"importance": {"$gte": min_importance}},
                ]
            },
            limit=50,  # Fetch more, then sort by importance
            include=["documents", "metadatas"],
        )

        items = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                items.append({
                    "content": doc,
                    "date": meta.get("date", "unknown"),
                    "importance": meta.get("importance", 0.5),
                    "type": meta.get("type", "unknown"),
                })

        # Sort by importance, return top N
        items.sort(key=lambda x: -x.get("importance", 0))
        return items[:max_n]

    except Exception as e:
        logger.debug("Window query failed (%d-%d days): %s", start_days, end_days, e)
        return []


def _query_milestones_in_window(
    episodic, start_days: int, end_days: int, max_n: int, min_importance: float
) -> List[Dict[str, Any]]:
    """Query milestones within a time window, sorted by importance."""
    now = datetime.now()
    start_date = (now - timedelta(days=end_days)).isoformat()
    end_date = (now - timedelta(days=start_days)).isoformat()

    try:
        results = episodic.milestones_collection.get(
            where={
                "$and": [
                    {"timestamp": {"$gte": start_date}},
                    {"timestamp": {"$lte": end_date}},
                    {"importance": {"$gte": min_importance}},
                ]
            },
            limit=50,
            include=["documents", "metadatas"],
        )

        items = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                items.append({
                    "content": doc,
                    "date": meta.get("timestamp", "unknown")[:10],
                    "importance": meta.get("importance", 0.5),
                    "type": meta.get("type", "milestone"),
                })

        items.sort(key=lambda x: -x.get("importance", 0))
        return items[:max_n]

    except Exception as e:
        logger.debug("Milestone window query failed (%d-%d days): %s", start_days, end_days, e)
        return []


def format_temporal_digest(items: List[Dict[str, Any]]) -> str:
    """Format temporal sweep results for boot output."""
    if not items:
        return ""

    lines = []

    # Group landmarks separately
    landmarks = [i for i in items if i.get("source") == "landmark"]
    memories = [i for i in items if i.get("source") != "landmark"]

    if landmarks:
        for lm in landmarks:
            content = lm["content"][:120]
            lines.append(f"[LANDMARK] {content}")

    if memories:
        for mem in memories:
            date = mem.get("date", "?")
            content = mem["content"][:120]
            source_tag = "M" if mem.get("source") == "milestone" else "R"
            lines.append(f"[{date}] [{source_tag}] {content}")

    return "\n".join(lines)


def boot_temporal_context() -> str:
    """
    Run temporal sweep and format for boot injection.
    Called from hooks/boot.py.
    """
    items = temporal_sweep()
    if not items:
        return ""

    digest = format_temporal_digest(items)
    if digest:
        return f"[LONG-RANGE MEMORY]\n{digest}"
    return ""
