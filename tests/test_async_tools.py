# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for Cortical async tool wrapper and concurrent dispatch."""

import asyncio
import functools
import threading
import time
import pytest

from concurrent.futures import ThreadPoolExecutor


class TestAsyncWrapper:
    """Test the sync→async wrapping pattern used in _app.py."""

    def test_sync_function_wrapped(self):
        """Sync function should be callable via run_in_executor."""
        def sync_fn(x, y):
            return x + y

        executor = ThreadPoolExecutor(max_workers=2)

        async def run():
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(executor, lambda: sync_fn(3, 4))
            return result

        result = asyncio.run(run())
        assert result == 7
        executor.shutdown(wait=False)

    def test_async_function_not_rewrapped(self):
        """Async functions should pass through without wrapping."""
        async def async_fn(x):
            return x * 2

        assert asyncio.iscoroutinefunction(async_fn)

        result = asyncio.run(async_fn(5))
        assert result == 10

    def test_wrapper_preserves_function_name(self):
        """functools.wraps should preserve the original name."""
        def original_function():
            pass

        @functools.wraps(original_function)
        async def wrapper(**kwargs):
            pass

        assert wrapper.__name__ == "original_function"

    def test_concurrent_dispatch(self):
        """Multiple sync functions should run concurrently in executor."""
        executor = ThreadPoolExecutor(max_workers=4)
        results = []
        lock = threading.Lock()

        def slow_fn(id, delay=0.05):
            time.sleep(delay)
            with lock:
                results.append(id)
            return f"done-{id}"

        async def run():
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(executor, lambda i=i: slow_fn(i))
                for i in range(4)
            ]
            return await asyncio.gather(*tasks)

        start = time.monotonic()
        outputs = asyncio.run(run())
        elapsed = time.monotonic() - start

        # 4 tasks at 50ms each should take ~50ms concurrent, not ~200ms serial
        assert elapsed < 0.15, f"Took {elapsed:.3f}s — not concurrent?"
        assert len(outputs) == 4
        assert all(o.startswith("done-") for o in outputs)
        executor.shutdown(wait=False)

    def test_exception_propagation(self):
        """Exceptions in sync functions should propagate through executor."""
        executor = ThreadPoolExecutor(max_workers=1)

        def failing_fn():
            raise ValueError("test error")

        async def run():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(executor, failing_fn)

        with pytest.raises(ValueError, match="test error"):
            asyncio.run(run())
        executor.shutdown(wait=False)

    def test_kwargs_passing(self):
        """Kwargs should be correctly passed through the lambda wrapper."""
        executor = ThreadPoolExecutor(max_workers=1)

        def tool_fn(action="list", n=5, query=None):
            return f"action={action} n={n} query={query}"

        async def run():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                executor, lambda: tool_fn(action="search", n=10, query="test")
            )

        result = asyncio.run(run())
        assert result == "action=search n=10 query=test"
        executor.shutdown(wait=False)


class TestToolRegistry:
    """Test that _TOOL_REGISTRY stores raw sync functions."""

    def test_registry_stores_sync(self):
        """_TOOL_REGISTRY should always store the raw sync function."""
        from elara_mcp._app import _TOOL_REGISTRY

        # Every function in the registry should be a regular function, not a coroutine
        for name, fn in _TOOL_REGISTRY.items():
            assert not asyncio.iscoroutinefunction(fn), (
                f"{name} in _TOOL_REGISTRY is async — should be raw sync"
            )
