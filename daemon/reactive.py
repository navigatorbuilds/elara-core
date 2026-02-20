# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Cortical Layer 1 — REACTIVE event processors.

Lightweight async handlers that subscribe to events and trigger
cascading effects. These run as fire-and-forget tasks on the
MCP event loop.

Processors:
  1. context_tracker — Update context cache on mood changes
  2. correction_matcher — Check for relevant corrections on tool dispatch
  3. mood_congruent — Surface mood-congruent memories on significant shifts
  4. episode_enricher — Update milestone index on episode notes
"""

import logging
from typing import List

from daemon.events import bus, Events, Event
from daemon.cache import cache, CacheKeys

logger = logging.getLogger("elara.reactive")

_initialized = False


def setup_reactive_processors() -> int:
    """Wire up all reactive processors. Returns count of subscriptions."""
    global _initialized
    if _initialized:
        return 0
    _initialized = True

    count = 0

    # --- 1. Context tracker ---
    # On mood change, invalidate context cache (mood is part of context)
    def _on_mood_for_context(event: Event):
        cache.invalidate(CacheKeys.CONTEXT_DATA)
        logger.debug("Context cache invalidated by %s", event.type)

    bus.on(Events.MOOD_CHANGED, _on_mood_for_context, priority=50, source="reactive.context")
    bus.on(Events.MOOD_SET, _on_mood_for_context, priority=50, source="reactive.context")
    count += 2

    # --- 2. Correction matcher ---
    # On correction added, invalidate the correction index cache
    def _on_correction_change(event: Event):
        cache.invalidate(CacheKeys.CORRECTION_INDEX)
        logger.debug("Correction index invalidated")

    bus.on(Events.CORRECTION_ADDED, _on_correction_change, priority=50, source="reactive.corrections")
    count += 1

    # --- 3. Mood congruent memory surfacing ---
    # On significant mood shift, log it for potential memory surfacing
    def _on_significant_mood_shift(event: Event):
        v_delta = abs(event.data.get("valence_delta", 0))
        e_delta = abs(event.data.get("energy_delta", 0))
        o_delta = abs(event.data.get("openness_delta", 0))
        max_delta = max(v_delta, e_delta, o_delta)

        if max_delta >= 0.15:
            logger.info(
                "Significant mood shift detected (delta=%.2f, reason=%s)",
                max_delta,
                event.data.get("reason", "unknown"),
            )

    bus.on(Events.MOOD_CHANGED, _on_significant_mood_shift, priority=30, source="reactive.mood")
    count += 1

    # --- 4. Episode enricher ---
    # On episode note, log for background index update
    def _on_episode_note(event: Event):
        note_type = event.data.get("note_type", "milestone")
        importance = event.data.get("importance", 0.5)
        if importance >= 0.7:
            logger.info(
                "High-importance %s recorded: %s",
                note_type,
                event.data.get("event", "")[:80],
            )

    bus.on(Events.EPISODE_NOTE_ADDED, _on_episode_note, priority=30, source="reactive.episodes")
    count += 1

    # --- 5. Goal change tracker ---
    def _on_goal_change(event: Event):
        cache.invalidate(CacheKeys.GOAL_LIST)

    bus.on(Events.GOAL_ADDED, _on_goal_change, priority=50, source="reactive.goals")
    bus.on(Events.GOAL_UPDATED, _on_goal_change, priority=50, source="reactive.goals")
    count += 2

    # --- 6. Dream completion ---
    def _on_dream_complete(event: Event):
        cache.invalidate(CacheKeys.DREAM_STATUS)
        logger.info("Dream completed: %s", event.data.get("dream_type", "?"))

    bus.on(Events.DREAM_COMPLETED, _on_dream_complete, priority=50, source="reactive.dreams")
    count += 1

    # --- 7. Brain integration ---
    def _on_brain_complete(event: Event):
        # Brain thinking changes many things — broad cache invalidation
        cache.clear()
        logger.info("Brain thinking completed — cache cleared")

    bus.on(Events.BRAIN_THINKING_COMPLETED, _on_brain_complete, priority=90, source="reactive.brain")
    count += 1

    logger.info("Reactive processors initialized: %d subscriptions", count)
    return count


def teardown_reactive_processors() -> None:
    """Remove all reactive processors. For testing."""
    global _initialized
    _initialized = False
