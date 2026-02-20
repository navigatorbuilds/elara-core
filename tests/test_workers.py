# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for Cortical Layer 2 — DELIBERATIVE worker pools."""

import asyncio
import threading
import time
import pytest

from daemon.workers import (
    WorkerPool,
    WorkerPoolBusy,
    WorkerManager,
    IO_TOOLS,
    LLM_TOOLS,
    get_pool_for_tool,
    MAX_QUEUE_DEPTH,
)


@pytest.fixture
def pool():
    p = WorkerPool("test", max_workers=2)
    yield p
    p.shutdown(wait=True)


@pytest.fixture
def manager():
    m = WorkerManager()
    yield m
    m.shutdown()


class TestWorkerPool:

    def test_submit_sync_returns_result(self, pool):
        future = pool.submit_sync(lambda: 42)
        assert future.result(timeout=2) == 42

    def test_submit_sync_with_args(self, pool):
        def add(a, b):
            return a + b
        future = pool.submit_sync(add, 3, 4)
        assert future.result(timeout=2) == 7

    def test_async_submit(self, pool):
        def compute():
            return "hello"

        async def run():
            return await pool.submit(compute)

        result = asyncio.run(run())
        assert result == "hello"

    def test_concurrent_execution(self, pool):
        results = []
        lock = threading.Lock()

        def slow(i):
            time.sleep(0.05)
            with lock:
                results.append(i)
            return i

        futures = [pool.submit_sync(slow, i) for i in range(2)]
        start = time.monotonic()
        for f in futures:
            f.result(timeout=2)
        elapsed = time.monotonic() - start

        # 2 tasks at 50ms on 2 workers = ~50ms, not ~100ms
        assert elapsed < 0.1
        assert len(results) == 2

    def test_stats_tracking(self, pool):
        pool.submit_sync(lambda: None).result(timeout=2)
        pool.submit_sync(lambda: None).result(timeout=2)

        stats = pool.stats()
        assert stats["name"] == "test"
        assert stats["submitted"] == 2
        assert stats["completed"] == 2
        assert stats["rejected"] == 0
        assert stats["pending"] == 0

    def test_exception_propagation(self, pool):
        def fail():
            raise RuntimeError("boom")

        future = pool.submit_sync(fail)
        with pytest.raises(RuntimeError, match="boom"):
            future.result(timeout=2)


class TestBackpressure:

    def test_rejects_when_full(self):
        pool = WorkerPool("tiny", max_workers=1)
        barrier = threading.Event()

        def block():
            barrier.wait(timeout=5)

        # Fill up the queue
        futures = []
        for _ in range(MAX_QUEUE_DEPTH):
            futures.append(pool.submit_sync(block))

        # Next submit should be rejected
        with pytest.raises(WorkerPoolBusy):
            pool.submit_sync(lambda: None)

        stats = pool.stats()
        assert stats["rejected"] == 1

        # Release all
        barrier.set()
        for f in futures:
            f.result(timeout=5)
        pool.shutdown(wait=True)

    def test_async_rejects_when_full(self):
        pool = WorkerPool("tiny", max_workers=1)
        barrier = threading.Event()

        def block():
            barrier.wait(timeout=5)

        futures = []
        for _ in range(MAX_QUEUE_DEPTH):
            futures.append(pool.submit_sync(block))

        async def run():
            return await pool.submit(lambda: None)

        with pytest.raises(WorkerPoolBusy):
            asyncio.run(run())

        barrier.set()
        for f in futures:
            f.result(timeout=5)
        pool.shutdown(wait=True)


class TestWorkerManager:

    def test_has_io_and_llm_pools(self, manager):
        assert manager.io is not None
        assert manager.llm is not None
        assert manager.io.max_workers == 4
        assert manager.llm.max_workers == 2

    def test_get_pool_by_name(self, manager):
        assert manager.get_pool("io") is manager.io
        assert manager.get_pool("llm") is manager.llm
        assert manager.get_pool("nope") is None

    def test_stats(self, manager):
        stats = manager.stats()
        assert "io" in stats
        assert "llm" in stats


class TestToolRouting:

    def test_io_tools_route_to_io(self):
        manager = WorkerManager()
        for tool in IO_TOOLS:
            pool = get_pool_for_tool(tool, manager)
            assert pool is manager.io, f"{tool} should route to io pool"
        manager.shutdown()

    def test_llm_tools_route_to_llm(self):
        manager = WorkerManager()
        for tool in LLM_TOOLS:
            pool = get_pool_for_tool(tool, manager)
            assert pool is manager.llm, f"{tool} should route to llm pool"
        manager.shutdown()

    def test_unknown_tool_routes_to_io(self):
        manager = WorkerManager()
        pool = get_pool_for_tool("elara_unknown", manager)
        assert pool is manager.io
        manager.shutdown()

    def test_none_manager_returns_none(self):
        assert get_pool_for_tool("elara_mood", None) is None
