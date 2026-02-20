# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for Cortical Layer 1 — REACTIVE event processors."""

import asyncio
import pytest

from daemon.events import EventBus, Events, Event
from daemon.cache import CorticalCache, CacheKeys


@pytest.fixture
def bus():
    return EventBus(history_size=50)


class TestDualModeEventBus:

    def test_sync_handler_works(self, bus):
        received = []
        bus.on("test", lambda e: received.append(e.data))
        bus.emit("test", {"val": 1})
        assert received == [{"val": 1}]

    def test_async_handler_detected(self, bus):
        async def async_handler(e):
            pass

        bus.on("test", async_handler)
        subs = bus.subscribers_for("test")
        assert subs[0]["is_async"] is True

    def test_sync_handler_detected(self, bus):
        bus.on("test", lambda e: None)
        subs = bus.subscribers_for("test")
        assert subs[0]["is_async"] is False

    def test_emit_async_calls_sync_handler(self):
        bus = EventBus()
        received = []
        bus.on("test", lambda e: received.append(e.data))

        asyncio.run(bus.emit_async("test", {"val": 42}))
        assert received == [{"val": 42}]

    def test_emit_async_awaits_async_handler(self):
        bus = EventBus()
        received = []

        async def handler(e):
            received.append(e.data)

        bus.on("test", handler)
        asyncio.run(bus.emit_async("test", {"val": 99}))
        assert received == [{"val": 99}]

    def test_mixed_sync_async_handlers(self):
        bus = EventBus()
        order = []

        def sync_handler(e):
            order.append("sync")

        async def async_handler(e):
            order.append("async")

        bus.on("test", sync_handler, priority=10)
        bus.on("test", async_handler, priority=5)

        asyncio.run(bus.emit_async("test", {}))
        assert order == ["sync", "async"]


class TestRecursionGuard:

    def test_recursion_depth_limited(self, bus):
        depth_reached = [0]

        def recursive_handler(e):
            depth_reached[0] += 1
            bus.emit("recursive", {"depth": depth_reached[0]})

        bus.on("recursive", recursive_handler)
        bus.emit("recursive", {"depth": 0})

        # Max depth is 3, so handler fires 3 times
        assert depth_reached[0] == 3

    def test_depth_resets_after_emit(self, bus):
        """After an emit chain completes, depth should reset."""
        count = [0]

        def handler(e):
            count[0] += 1

        bus.on("a", handler)

        # Two separate emit chains should both work
        bus.emit("a", {})
        bus.emit("a", {})
        assert count[0] == 2


class TestAsyncEmitViaSync:

    def test_sync_emit_schedules_async_in_running_loop(self):
        bus = EventBus()
        received = []

        async def async_handler(e):
            received.append(e.data["val"])

        bus.on("test", async_handler)

        async def run():
            bus.emit("test", {"val": 1})
            # Give the scheduled task a chance to run
            await asyncio.sleep(0.01)

        asyncio.run(run())
        assert received == [1]


class TestOnceAsync:

    def test_async_once_fires_once(self):
        bus = EventBus()
        count = []

        async def handler(e):
            count.append(1)

        bus.once("test", handler)

        async def run():
            await bus.emit_async("test", {})
            await bus.emit_async("test", {})

        asyncio.run(run())
        assert len(count) == 1


class TestStatsIncludeAsync:

    def test_stats_show_async_count(self, bus):
        async def async_h(e):
            pass

        bus.on("a", lambda e: None)
        bus.on("b", async_h)

        stats = bus.stats()
        assert stats["async_subscribers"] == 1
        assert stats["total_subscribers"] == 2


class TestBackwardCompat:
    """Verify all existing sync patterns still work identically."""

    def test_priority_ordering(self, bus):
        order = []
        bus.on("test", lambda e: order.append("low"), priority=0)
        bus.on("test", lambda e: order.append("high"), priority=10)
        bus.emit("test", {})
        assert order == ["high", "low"]

    def test_once_fires_once(self, bus):
        count = []
        bus.once("test", lambda e: count.append(1))
        bus.emit("test", {})
        bus.emit("test", {})
        assert len(count) == 1

    def test_off_unsubscribes(self, bus):
        handler = lambda e: None
        bus.on("test", handler)
        assert bus.off("test", handler) is True
        assert len(bus._subscribers["test"]) == 0

    def test_mute_unmute(self, bus):
        received = []
        bus.on("test", lambda e: received.append(1))
        bus.mute("test")
        bus.emit("test", {})
        assert len(received) == 0
        bus.unmute("test")
        bus.emit("test", {})
        assert len(received) == 1

    def test_history(self, bus):
        bus.emit("a", {"x": 1})
        bus.emit("b", {"x": 2})
        assert len(bus._history) == 2

    def test_bad_handler_doesnt_stop_others(self, bus):
        results = []

        def bad(e):
            raise RuntimeError("boom")

        bus.on("test", bad, priority=10)
        bus.on("test", lambda e: results.append("ok"), priority=0)
        bus.emit("test", {})
        assert results == ["ok"]
