# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Shared FastMCP application instance and profile-aware tool registration.

Profile system:
  - "full"  — all tools registered as individual MCP schemas (~22% context)
  - "lean"  — 7 core tools + 1 elara_do meta-tool (~5% context)

In both modes, every tool function is stored in _TOOL_REGISTRY so
elara_do can dispatch to any tool by name.
"""

import functools
import logging
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

    - Always stores the function in _TOOL_REGISTRY.
    - In "full" mode: also registers via @mcp.tool() (all schemas visible).
    - In "lean" mode: only registers core tools via @mcp.tool().
    """
    def decorator(fn):
        name = fn.__name__
        _TOOL_REGISTRY[name] = fn

        if _PROFILE == "full" or name in _CORE_TOOLS:
            return mcp.tool()(fn)

        # lean mode, non-core: just return the raw function (no MCP schema)
        return fn

    return decorator
