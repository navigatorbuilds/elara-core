# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tier 3: Event bus tests — dispatch, priority, mute, threading."""

import threading
import pytest

from daemon.events import EventBus, Events, Event


@pytest.fixture
def bus():
    return EventBus(history_size=50)


class TestBasicDispatch:

    def test_emit_calls_subscriber(self, bus):
        received = []
        bus.on("test", lambda e: received.append(e.data))
        bus.emit("test", {"val": 42})
        assert len(received) == 1
        assert received[0]["val"] == 42

    def test_emit_returns_event(self, bus):
        event = bus.emit("test", {"x": 1})
        assert isinstance(event, Event)
        assert event.type == "test"
        assert event.data["x"] == 1

    def test_no_subscribers_no_crash(self, bus):
        event = bus.emit("nobody_listening", {"ok": True})
        assert event.type == "nobody_listening"

    def test_multiple_subscribers(self, bus):
        results = []
        bus.on("test", lambda e: results.append("a"))
        bus.on("test", lambda e: results.append("b"))
        bus.emit("test", {})
        assert len(results) == 2


class TestPriority:

    def test_higher_priority_first(self, bus):
        order = []
        bus.on("test", lambda e: order.append("low"), priority=0)
        bus.on("test", lambda e: order.append("high"), priority=10)
        bus.emit("test", {})
        assert order == ["high", "low"]

    def test_equal_priority_preserves_order(self, bus):
        order = []
        bus.on("test", lambda e: order.append("first"), priority=5)
        bus.on("test", lambda e: order.append("second"), priority=5)
        bus.emit("test", {})
        assert order == ["first", "second"]


class TestOnce:

    def test_once_fires_once(self, bus):
        count = []
        bus.once("test", lambda e: count.append(1))
        bus.emit("test", {})
        bus.emit("test", {})
        assert len(count) == 1

    def test_once_removed_after_fire(self, bus):
        bus.once("test", lambda e: None)
        bus.emit("test", {})
        # Should have no subscribers left
        assert len(bus._subscribers.get("test", [])) == 0


class TestOff:

    def test_unsubscribe(self, bus):
        handler = lambda e: None
        bus.on("test", handler)
        assert bus.off("test", handler) is True
        assert len(bus._subscribers["test"]) == 0

    def test_unsubscribe_nonexistent(self, bus):
        assert bus.off("test", lambda e: None) is False


class TestMute:

    def test_muted_event_not_dispatched(self, bus):
        received = []
        bus.on("test", lambda e: received.append(1))
        bus.mute("test")
        bus.emit("test", {})
        assert len(received) == 0

    def test_unmute_resumes_dispatch(self, bus):
        received = []
        bus.on("test", lambda e: received.append(1))
        bus.mute("test")
        bus.emit("test", {})
        bus.unmute("test")
        bus.emit("test", {})
        assert len(received) == 1

    def test_muted_event_still_in_history(self, bus):
        bus.mute("test")
        bus.emit("test", {"muted": True})
        assert len(bus._history) == 1


class TestHistory:

    def test_history_records_events(self, bus):
        bus.emit("a", {"x": 1})
        bus.emit("b", {"x": 2})
        assert len(bus._history) == 2

    def test_history_caps_at_size(self):
        bus = EventBus(history_size=3)
        for i in range(10):
            bus.emit("test", {"i": i})
        assert len(bus._history) == 3
        assert bus._history[0].data["i"] == 7  # Oldest kept


class TestErrorHandling:

    def test_bad_handler_doesnt_stop_others(self, bus):
        results = []

        def bad(e):
            raise RuntimeError("boom")

        bus.on("test", bad, priority=10)
        bus.on("test", lambda e: results.append("ok"), priority=0)
        bus.emit("test", {})
        assert results == ["ok"]


class TestThreadSafety:

    def test_concurrent_emits(self, bus):
        count = {"n": 0}
        lock = threading.Lock()

        def handler(e):
            with lock:
                count["n"] += 1

        bus.on("test", handler)

        threads = [threading.Thread(target=bus.emit, args=("test", {})) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert count["n"] == 100
