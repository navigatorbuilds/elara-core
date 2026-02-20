# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for Cortical Layer 0 — REFLEX cache."""

import threading
import time
import pytest

from daemon.cache import CorticalCache, CacheKeys, CACHE_TTLS


@pytest.fixture
def cache():
    return CorticalCache()


class TestBasicOps:

    def test_set_and_get(self, cache):
        cache.set("key1", "value1", ttl=10.0)
        assert cache.get("key1") == "value1"

    def test_get_miss_returns_none(self, cache):
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, cache):
        cache.set("short", "data", ttl=0.05)
        assert cache.get("short") == "data"
        time.sleep(0.06)
        assert cache.get("short") is None

    def test_overwrite(self, cache):
        cache.set("key", "v1", ttl=10.0)
        cache.set("key", "v2", ttl=10.0)
        assert cache.get("key") == "v2"

    def test_complex_values(self, cache):
        data = {"mood": {"valence": 0.5}, "list": [1, 2, 3]}
        cache.set("complex", data, ttl=10.0)
        assert cache.get("complex") == data


class TestInvalidation:

    def test_invalidate_single(self, cache):
        cache.set("a", 1, ttl=10.0)
        removed = cache.invalidate("a")
        assert removed == 1
        assert cache.get("a") is None

    def test_invalidate_multiple(self, cache):
        cache.set("a", 1, ttl=10.0)
        cache.set("b", 2, ttl=10.0)
        cache.set("c", 3, ttl=10.0)
        removed = cache.invalidate("a", "b")
        assert removed == 2
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_invalidate_nonexistent(self, cache):
        removed = cache.invalidate("nope")
        assert removed == 0

    def test_clear(self, cache):
        cache.set("a", 1, ttl=10.0)
        cache.set("b", 2, ttl=10.0)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


class TestStats:

    def test_hit_miss_tracking(self, cache):
        cache.set("key", "val", ttl=10.0)
        cache.get("key")       # hit
        cache.get("key")       # hit
        cache.get("missing")   # miss

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert stats["entries"] == 1

    def test_invalidation_count(self, cache):
        cache.set("a", 1, ttl=10.0)
        cache.invalidate("a")
        assert cache.stats()["invalidations"] == 1


class TestGetOrCompute:

    def test_caches_on_miss(self, cache):
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return {"computed": True}

        result1 = cache.get_or_compute("key", 10.0, compute)
        result2 = cache.get_or_compute("key", 10.0, compute)

        assert result1 == {"computed": True}
        assert result2 == {"computed": True}
        assert call_count == 1  # only computed once

    def test_recomputes_after_expiry(self, cache):
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return call_count

        cache.get_or_compute("key", 0.05, compute)
        time.sleep(0.06)
        result = cache.get_or_compute("key", 0.05, compute)

        assert result == 2
        assert call_count == 2


class TestThreadSafety:

    def test_concurrent_writes(self, cache):
        errors = []

        def writer(i):
            try:
                for j in range(100):
                    cache.set(f"key-{i}-{j}", j, ttl=10.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_read_write(self, cache):
        cache.set("shared", 0, ttl=60.0)
        errors = []

        def reader():
            try:
                for _ in range(200):
                    cache.get("shared")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(200):
                    cache.set("shared", i, ttl=60.0)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_invalidation(self, cache):
        for i in range(50):
            cache.set(f"k{i}", i, ttl=60.0)

        errors = []

        def invalidator():
            try:
                for i in range(50):
                    cache.invalidate(f"k{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=invalidator) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCacheConstants:

    def test_all_keys_have_ttls(self):
        """Every CacheKey constant must have a TTL defined."""
        for attr in dir(CacheKeys):
            if attr.startswith("_"):
                continue
            key = getattr(CacheKeys, attr)
            assert key in CACHE_TTLS, f"Missing TTL for CacheKeys.{attr}"

    def test_ttls_are_positive(self):
        for key, ttl in CACHE_TTLS.items():
            assert ttl > 0, f"TTL for {key} must be positive"
