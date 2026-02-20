# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Event Bus — Decoupled pub/sub for cross-module communication.

Cortical Layer 1 — REACTIVE: Dual-mode event bus supporting both
synchronous and asynchronous handlers.

Instead of modules importing and calling each other directly:
    from daemon.goals import stale_goals  # tight coupling

They emit/subscribe to events:
    bus.emit("goal_stalled", {"goal_id": 1, "days": 14})  # loose coupling

Core design:
- Dual dispatch: sync handlers called inline, async handlers scheduled
- Typed events with payload schemas
- Subscriber priority ordering
- Event history for debugging
- Thread-safe for concurrent tool execution
- Recursion depth limit (max 3) as safety valve

Usage:
    from daemon.events import bus, Events

    # Subscribe (sync — same as before)
    bus.on(Events.MOOD_CHANGED, my_handler)
    bus.on(Events.MOOD_CHANGED, my_handler, priority=10)

    # Subscribe (async — new)
    async def my_async_handler(event):
        await some_io_operation(event.data)
    bus.on(Events.MOOD_CHANGED, my_async_handler)

    # Emit (sync — backward compatible, schedules async handlers)
    bus.emit(Events.MOOD_CHANGED, {"valence": 0.6, "energy": 0.4})

    # Emit async (new — awaits async handlers)
    await bus.emit_async(Events.MOOD_CHANGED, {"valence": 0.6})

    # One-shot listener
    bus.once(Events.SESSION_ENDED, cleanup_handler)
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger("elara.events")

# Recursion safety — max emit depth before refusing
_MAX_EMIT_DEPTH = 3


# ============================================================================
# EVENT TYPES — All known events in Elara
# ============================================================================

class Events:
    """Registry of all event types. Use these constants, not raw strings."""

    # --- Mood & State ---
    MOOD_CHANGED = "mood_changed"
    MOOD_SET = "mood_set"
    IMPRINT_CREATED = "imprint_created"
    IMPRINT_DECAYED = "imprint_decayed"
    TEMPERAMENT_UPDATED = "temperament_updated"

    # --- Session Lifecycle ---
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    EPISODE_STARTED = "episode_started"
    EPISODE_ENDED = "episode_ended"
    EPISODE_NOTE_ADDED = "episode_note_added"

    # --- Goals & Corrections ---
    GOAL_ADDED = "goal_added"
    GOAL_UPDATED = "goal_updated"
    GOAL_STALLED = "goal_stalled"
    CORRECTION_ADDED = "correction_added"
    CORRECTION_ACTIVATED = "correction_activated"

    # --- Memory ---
    MEMORY_SAVED = "memory_saved"
    MEMORY_RECALLED = "memory_recalled"
    MEMORY_CONSOLIDATED = "memory_consolidated"
    MEMORY_ARCHIVED = "memory_archived"
    CONVERSATION_INGESTED = "conversation_ingested"

    # --- Awareness ---
    BLIND_SPOT_DETECTED = "blind_spot_detected"
    REFLECTION_COMPLETED = "reflection_completed"
    PULSE_GENERATED = "pulse_generated"
    OBSERVATION_SURFACED = "observation_surfaced"
    INTENTION_SET = "intention_set"

    # --- Dreams ---
    DREAM_STARTED = "dream_started"
    DREAM_COMPLETED = "dream_completed"

    # --- Reasoning & Outcomes ---
    TRAIL_STARTED = "trail_started"
    TRAIL_SOLVED = "trail_solved"
    OUTCOME_RECORDED = "outcome_recorded"
    OUTCOME_CHECKED = "outcome_checked"

    # --- Synthesis & Business ---
    SYNTHESIS_CREATED = "synthesis_created"
    SEED_ADDED = "seed_added"
    IDEA_CREATED = "idea_created"
    IDEA_SCORED = "idea_scored"

    # --- Overwatch ---
    INJECTION_FOUND = "injection_found"

    # --- LLM (Ollama) ---
    LLM_QUERY = "llm_query"
    LLM_TRIAGE = "llm_triage"
    LLM_UNAVAILABLE = "llm_unavailable"

    # --- 3D Cognition ---
    MODEL_CREATED = "model_created"
    MODEL_UPDATED = "model_updated"
    MODEL_INVALIDATED = "model_invalidated"
    PREDICTION_MADE = "prediction_made"
    PREDICTION_CHECKED = "prediction_checked"
    PRINCIPLE_CRYSTALLIZED = "principle_crystallized"
    PRINCIPLE_CONFIRMED = "principle_confirmed"
    PRINCIPLE_CHALLENGED = "principle_challenged"

    # --- Workflows ---
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_MATCHED = "workflow_matched"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_RETIRED = "workflow_retired"

    # --- Handoff ---
    HANDOFF_SAVED = "handoff_saved"

    # --- Layer 1 Bridge ---
    ARTIFACT_VALIDATED = "artifact_validated"

    # --- Layer 2 Network ---
    RECORD_RECEIVED = "record_received"
    RECORD_WITNESSED = "record_witnessed"
    ATTESTATION_VERIFIED = "attestation_verified"
    PEER_DISCOVERED = "peer_discovered"
    PEER_LOST = "peer_lost"
    PEER_RATE_LIMITED = "peer_rate_limited"
    NETWORK_STARTED = "network_started"
    NETWORK_STOPPED = "network_stopped"

    # --- Cortical Layer 3 — Brain ---
    BRAIN_THINKING_STARTED = "brain_thinking_started"
    BRAIN_THINKING_COMPLETED = "brain_thinking_completed"


# ============================================================================
# EVENT DATA
# ============================================================================

@dataclass
class Event:
    """A single emitted event."""
    type: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: Optional[str] = None  # module that emitted


# ============================================================================
# SUBSCRIBER
# ============================================================================

@dataclass
class Subscriber:
    """A registered event handler."""
    callback: Callable[[Event], None]
    priority: int = 0  # higher = called first
    once: bool = False  # auto-remove after first call
    source: Optional[str] = None  # for debugging
    is_async: bool = False  # auto-detected from callback


# ============================================================================
# EVENT BUS
# ============================================================================

class EventBus:
    """
    Central event bus for Elara — Cortical Layer 1.

    Dual-mode dispatch: sync handlers inline, async handlers scheduled.
    Priority-ordered with history. Thread-safe via lock.
    """

    def __init__(self, history_size: int = 100):
        self._subscribers: Dict[str, List[Subscriber]] = {}
        self._history: List[Event] = []
        self._history_size = history_size
        self._lock = threading.Lock()
        self._muted: Set[str] = set()
        self._emit_count = 0
        self._emit_depth = 0  # recursion guard

    def on(
        self,
        event_type: str,
        callback: Callable,
        priority: int = 0,
        source: Optional[str] = None,
    ) -> None:
        """
        Subscribe to an event type. Accepts both sync and async callbacks.

        Args:
            event_type: Event type string (use Events.* constants)
            callback: Function called with Event when fired (sync or async)
            priority: Higher = called first (default 0)
            source: Optional label for debugging
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            sub = Subscriber(
                callback=callback,
                priority=priority,
                source=source,
                is_async=asyncio.iscoroutinefunction(callback),
            )
            self._subscribers[event_type].append(sub)
            self._subscribers[event_type].sort(key=lambda s: -s.priority)

    def once(
        self,
        event_type: str,
        callback: Callable,
        priority: int = 0,
        source: Optional[str] = None,
    ) -> None:
        """Subscribe to an event, auto-remove after first call."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            sub = Subscriber(
                callback=callback,
                priority=priority,
                once=True,
                source=source,
                is_async=asyncio.iscoroutinefunction(callback),
            )
            self._subscribers[event_type].append(sub)
            self._subscribers[event_type].sort(key=lambda s: -s.priority)

    def off(self, event_type: str, callback: Callable) -> bool:
        """Unsubscribe a callback. Returns True if found and removed."""
        with self._lock:
            if event_type not in self._subscribers:
                return False
            before = len(self._subscribers[event_type])
            self._subscribers[event_type] = [
                s for s in self._subscribers[event_type]
                if s.callback is not callback
            ]
            return len(self._subscribers[event_type]) < before

    def emit(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Event:
        """
        Emit an event — backward compatible sync dispatch.

        Sync handlers: called inline (same as before).
        Async handlers: scheduled via asyncio.create_task() if a loop
        is running, otherwise skipped with a warning.

        Args:
            event_type: Event type (use Events.* constants)
            data: Event payload dict
            source: Module name that emitted this event

        Returns:
            The Event object that was dispatched
        """
        event = Event(
            type=event_type,
            data=data or {},
            source=source,
        )

        # Recursion guard
        self._emit_depth += 1
        if self._emit_depth > _MAX_EMIT_DEPTH:
            logger.warning(
                "Event recursion depth %d exceeded for %s — skipping",
                self._emit_depth, event_type,
            )
            self._emit_depth -= 1
            return event

        try:
            with self._lock:
                self._emit_count += 1

                # Record in history
                self._history.append(event)
                if len(self._history) > self._history_size:
                    self._history = self._history[-self._history_size:]

                # Skip if muted
                if event_type in self._muted:
                    return event

                # Get subscribers (copy to avoid mutation during iteration)
                subs = list(self._subscribers.get(event_type, []))

            # Dispatch outside lock to prevent deadlocks
            to_remove = []
            for sub in subs:
                try:
                    if sub.is_async:
                        # Schedule async handler if loop is running
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(sub.callback(event))
                        except RuntimeError:
                            # No running loop — skip async handler
                            logger.debug(
                                "No event loop for async handler %s on %s",
                                sub.source or sub.callback.__name__,
                                event_type,
                            )
                    else:
                        sub.callback(event)
                except Exception as e:
                    logger.error(
                        "Event handler error: %s -> %s: %s",
                        event_type,
                        sub.source or sub.callback.__name__,
                        e,
                    )
                if sub.once:
                    to_remove.append(sub)

            # Clean up one-shot subscribers
            if to_remove:
                with self._lock:
                    for sub in to_remove:
                        try:
                            self._subscribers[event_type].remove(sub)
                        except (ValueError, KeyError):
                            pass

            return event
        finally:
            self._emit_depth -= 1

    async def emit_async(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Event:
        """
        Emit an event — async dispatch. Awaits async handlers,
        calls sync handlers directly.

        Use this from async code paths for full handler execution.
        """
        event = Event(
            type=event_type,
            data=data or {},
            source=source,
        )

        # Recursion guard
        self._emit_depth += 1
        if self._emit_depth > _MAX_EMIT_DEPTH:
            logger.warning(
                "Event recursion depth %d exceeded for %s — skipping",
                self._emit_depth, event_type,
            )
            self._emit_depth -= 1
            return event

        try:
            with self._lock:
                self._emit_count += 1
                self._history.append(event)
                if len(self._history) > self._history_size:
                    self._history = self._history[-self._history_size:]
                if event_type in self._muted:
                    return event
                subs = list(self._subscribers.get(event_type, []))

            to_remove = []
            for sub in subs:
                try:
                    if sub.is_async:
                        await sub.callback(event)
                    else:
                        sub.callback(event)
                except Exception as e:
                    logger.error(
                        "Event handler error: %s -> %s: %s",
                        event_type,
                        sub.source or sub.callback.__name__,
                        e,
                    )
                if sub.once:
                    to_remove.append(sub)

            if to_remove:
                with self._lock:
                    for sub in to_remove:
                        try:
                            self._subscribers[event_type].remove(sub)
                        except (ValueError, KeyError):
                            pass

            return event
        finally:
            self._emit_depth -= 1

    def mute(self, event_type: str) -> None:
        """Temporarily stop dispatching an event type."""
        with self._lock:
            self._muted.add(event_type)

    def unmute(self, event_type: str) -> None:
        """Resume dispatching an event type."""
        with self._lock:
            self._muted.discard(event_type)

    # --- Introspection ---

    def subscribers_for(self, event_type: str) -> List[Dict[str, Any]]:
        """List subscribers for an event type (for debugging)."""
        with self._lock:
            return [
                {
                    "callback": s.callback.__name__,
                    "priority": s.priority,
                    "once": s.once,
                    "source": s.source,
                    "is_async": s.is_async,
                }
                for s in self._subscribers.get(event_type, [])
            ]

    def history(self, event_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent event history."""
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e.type == event_type]
            return [
                {
                    "type": e.type,
                    "data": e.data,
                    "timestamp": e.timestamp,
                    "source": e.source,
                }
                for e in events[-limit:]
            ]

    def stats(self) -> Dict[str, Any]:
        """Bus statistics."""
        with self._lock:
            sub_counts = {
                k: len(v) for k, v in self._subscribers.items() if v
            }
            async_count = sum(
                1 for subs in self._subscribers.values()
                for s in subs if s.is_async
            )
            return {
                "total_emitted": self._emit_count,
                "history_size": len(self._history),
                "subscriber_counts": sub_counts,
                "total_subscribers": sum(sub_counts.values()),
                "async_subscribers": async_count,
                "muted_events": list(self._muted),
            }

    def reset(self) -> None:
        """Clear all subscribers and history. For testing."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()
            self._muted.clear()
            self._emit_count = 0
            self._emit_depth = 0


# ============================================================================
# SINGLETON — the global event bus
# ============================================================================

bus = EventBus()
