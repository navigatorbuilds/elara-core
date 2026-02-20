# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Cortical Layer 2 — DELIBERATIVE worker pools.

Specialized thread pools for heavy operations with backpressure:
  - io: 4 threads — ChromaDB, file I/O, SQLite
  - llm: 2 threads — Ollama, Gmail API, RSS feeds

Why threads not processes: ChromaDB PersistentClient can't be pickled,
all ops are I/O-bound (GIL not a bottleneck).

Backpressure: Queue depth > MAX_QUEUE_DEPTH -> WorkerPoolBusy exception.
Callers fall back to blocking execution.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("elara.workers")

MAX_QUEUE_DEPTH = 32


class WorkerPoolBusy(Exception):
    """Raised when a worker pool's queue is full."""
    pass


class WorkerPool:
    """A named thread pool with queue depth tracking."""

    def __init__(self, name: str, max_workers: int):
        self.name = name
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"elara-{name}",
        )
        self._pending = 0
        self._lock = threading.Lock()
        self._total_submitted = 0
        self._total_completed = 0
        self._total_rejected = 0

    def submit_sync(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit work to the pool. Raises WorkerPoolBusy if overloaded."""
        with self._lock:
            if self._pending >= MAX_QUEUE_DEPTH:
                self._total_rejected += 1
                raise WorkerPoolBusy(
                    f"Pool '{self.name}' full ({self._pending}/{MAX_QUEUE_DEPTH})"
                )
            self._pending += 1
            self._total_submitted += 1

        def _tracked(*a, **kw):
            try:
                return fn(*a, **kw)
            finally:
                with self._lock:
                    self._pending -= 1
                    self._total_completed += 1

        return self._executor.submit(_tracked, *args, **kwargs)

    async def submit(self, fn: Callable, **kwargs) -> Any:
        """Async submit — awaits result. Raises WorkerPoolBusy."""
        with self._lock:
            if self._pending >= MAX_QUEUE_DEPTH:
                self._total_rejected += 1
                raise WorkerPoolBusy(
                    f"Pool '{self.name}' full ({self._pending}/{MAX_QUEUE_DEPTH})"
                )
            self._pending += 1
            self._total_submitted += 1

        def _run():
            try:
                return fn(**kwargs)
            finally:
                with self._lock:
                    self._pending -= 1
                    self._total_completed += 1

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _run)

    def stats(self) -> Dict[str, Any]:
        """Pool statistics."""
        with self._lock:
            return {
                "name": self.name,
                "max_workers": self.max_workers,
                "pending": self._pending,
                "submitted": self._total_submitted,
                "completed": self._total_completed,
                "rejected": self._total_rejected,
            }

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the pool."""
        self._executor.shutdown(wait=wait)
        logger.info("Worker pool '%s' shut down", self.name)


class WorkerManager:
    """Manages all worker pools for the cortical execution model."""

    def __init__(self):
        self.io = WorkerPool("io", max_workers=4)
        self.llm = WorkerPool("llm", max_workers=2)
        self._pools = {"io": self.io, "llm": self.llm}

    def get_pool(self, name: str) -> Optional[WorkerPool]:
        """Get a pool by name."""
        return self._pools.get(name)

    def stats(self) -> Dict[str, Any]:
        """Stats for all pools."""
        return {name: pool.stats() for name, pool in self._pools.items()}

    def shutdown(self) -> None:
        """Shut down all pools."""
        for pool in self._pools.values():
            pool.shutdown(wait=False)
        logger.info("All worker pools shut down")


# ---------------------------------------------------------------------------
# Tool → pool routing
# ---------------------------------------------------------------------------

# Tools that should use the IO pool (ChromaDB, file I/O, SQLite)
IO_TOOLS = frozenset({
    "elara_remember",
    "elara_recall",
    "elara_recall_conversation",
    "elara_conversations",
    "elara_kg_index",
    "elara_kg_query",
    "elara_kg_validate",
    "elara_kg_diff",
    "elara_rebuild_indexes",
    "elara_memory_consolidation",
    "elara_model",
    "elara_prediction",
    "elara_principle",
    "elara_workflow",
    "elara_reasoning",
    "elara_outcome",
    "elara_synthesis",
})

# Tools that should use the LLM pool (Ollama, Gmail, RSS)
LLM_TOOLS = frozenset({
    "elara_llm",
    "elara_gmail",
    "elara_briefing",
    "elara_dream",
    "elara_dream_info",
})


def get_pool_for_tool(tool_name: str, manager: Optional[WorkerManager]) -> Optional[WorkerPool]:
    """Route a tool to the appropriate worker pool."""
    if manager is None:
        return None
    if tool_name in IO_TOOLS:
        return manager.io
    if tool_name in LLM_TOOLS:
        return manager.llm
    # Default: use IO pool for everything else
    return manager.io


# ---------------------------------------------------------------------------
# SINGLETON — initialized by server.py
# ---------------------------------------------------------------------------

workers: Optional[WorkerManager] = None


def init_workers() -> WorkerManager:
    """Initialize the global worker manager."""
    global workers
    workers = WorkerManager()
    logger.info(
        "Worker pools initialized: io=%d, llm=%d",
        workers.io.max_workers, workers.llm.max_workers,
    )
    return workers


def shutdown_workers() -> None:
    """Shut down the global worker manager."""
    global workers
    if workers:
        workers.shutdown()
        workers = None
