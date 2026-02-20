# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Shared FastMCP application instance and profile-aware tool registration.

Profile system:
  - "full"  — all tools registered as individual MCP schemas (~22% context)
  - "lean"  — 7 core tools + 1 elara_do meta-tool (~5% context)

Cortical Execution Model:
  All sync tool handlers are wrapped in async def + run_in_executor so
  concurrent MCP calls don't block each other. The raw sync function is
  kept in _TOOL_REGISTRY for elara_do direct dispatch.

In both modes, every tool function is stored in _TOOL_REGISTRY so
elara_do can dispatch to any tool by name.
"""

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.paths import get_paths

# Central logging config — all elara.* loggers route here
_log_path = get_paths().daemon_log
_log_path.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(_log_path)),
    ],
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("elara")

# ---------------------------------------------------------------------------
# Cortical Layer 2 — DELIBERATIVE executor (default pool)
# Specialized pools are in daemon/workers.py; this is the fallback.
# ---------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="elara-tool")

logger = logging.getLogger("elara.app")

# ---------------------------------------------------------------------------
# Profile system
# ---------------------------------------------------------------------------

_PROFILE: str = "lean"  # default; overridden by set_profile() before imports

_CORE_TOOLS: frozenset = frozenset({
    "elara_mood",
    "elara_status",
    "elara_remember",
    "elara_recall",
    "elara_recall_conversation",
    "elara_context",
    "elara_handoff",
})

# Every tool function is stored here regardless of profile.
# Keys are the function name (e.g. "elara_goal"), values are the callable.
# Values are always the RAW SYNC function, even when an async wrapper is
# registered with MCP. This lets elara_do dispatch directly.
_TOOL_REGISTRY: dict = {}


def set_profile(profile: str) -> None:
    """Set the tool profile before tool modules are imported."""
    global _PROFILE
    _PROFILE = profile


def get_profile() -> str:
    """Return the current profile."""
    return _PROFILE


def tool():
    """Profile-aware decorator replacing @mcp.tool().

    - Always stores the raw sync function in _TOOL_REGISTRY.
    - Wraps sync functions in async def + run_in_executor for MCP registration.
    - In "full" mode: registers async wrapper via @mcp.tool() (all schemas visible).
    - In "lean" mode: only registers core tools via @mcp.tool().
    """
    def decorator(fn):
        name = fn.__name__
        # Always store the raw sync function for elara_do
        _TOOL_REGISTRY[name] = fn

        if _PROFILE == "full" or name in _CORE_TOOLS:
            # Wrap sync → async for non-blocking MCP dispatch
            if not asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(**kwargs):
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        _executor, lambda: fn(**kwargs)
                    )
                register_fn = async_wrapper
            else:
                register_fn = fn
            return mcp.tool()(register_fn)

        # lean mode, non-core: just return the raw function (no MCP schema)
        return fn

    return decorator


def shutdown_executor() -> None:
    """Graceful shutdown of the tool executor pool."""
    _executor.shutdown(wait=False)
    logger.info("Tool executor pool shut down")
