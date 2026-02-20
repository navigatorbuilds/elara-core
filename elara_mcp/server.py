#!/usr/bin/env python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara MCP Server

Tools are organized into domain modules under elara_mcp/tools/.
Importing each module registers its tools via the profile-aware @tool() decorator.

Cortical Execution Model:
  Layer 0 — REFLEX:       Hot cache, instant reads (daemon/cache.py)
  Layer 1 — REACTIVE:     Async event handlers (daemon/reactive.py)
  Layer 2 — DELIBERATIVE: Worker pools for heavy I/O (daemon/workers.py)
  Layer 3 — CONTEMPLATIVE: Overnight brain (daemon/overnight/)
  Layer 4 — SOCIAL:       Peer network (network/)

Tier System (hardware capability gating):
  Tier 0 — VALIDATE:  Crypto + DAG only (IoT, embedded)
  Tier 1 — REMEMBER:  + memory, episodes, goals, maintenance
  Tier 2 — THINK:     + mood, awareness, dreams, cognitive, etc. (DEFAULT)
  Tier 3 — CONNECT:   + network (full mesh)

  Tier controls which modules LOAD. Profile controls which loaded tools
  get MCP schemas. They're orthogonal.

Profiles:
  --profile full  → 39 individual tool schemas (backward compatible)
  --profile lean  → 7 core schemas + 1 elara_do meta-tool (default, ~5% context)

45 tools across 15 modules:
- memory:       elara_remember, elara_recall, elara_recall_conversation, elara_conversations (4)
- mood:         elara_mood, elara_mood_adjust, elara_imprint, elara_mode, elara_status (5)
- episodes:     elara_episode_start, elara_episode_note, elara_episode_end, elara_episode_query, elara_context (5)
- goals:        elara_goal, elara_goal_boot, elara_correction, elara_correction_boot, elara_handoff (5)
- awareness:    elara_reflect, elara_insight, elara_intention, elara_observe, elara_temperament (5)
- dreams:       elara_dream, elara_dream_info (2)
- cognitive:    elara_reasoning, elara_outcome, elara_synthesis (3)
- cognition_3d: elara_model, elara_prediction, elara_principle (3)
- workflows:    elara_workflow (1)
- knowledge:    elara_kg_index, elara_kg_query, elara_kg_validate, elara_kg_diff (4)
- business:     elara_business (1)
- llm:          elara_llm (1)
- gmail:        elara_gmail (1)
- maintenance:  elara_rebuild_indexes, elara_briefing, elara_snapshot, elara_memory_consolidation (4)
- network:      elara_network (1)
"""

import atexit
import logging
import os as _os
import sys as _sys

from elara_mcp._app import mcp, get_profile, set_profile, shutdown_executor

logger = logging.getLogger("elara.server")

# Allow profile override via env var (used by MCP stdio config).
# Must happen before tool module imports — @tool() reads the profile.
_env_profile = _os.environ.get("ELARA_PROFILE")
if _env_profile and _env_profile != get_profile():
    set_profile(_env_profile)

# ---------------------------------------------------------------------------
# Tier-gated tool module imports
# ---------------------------------------------------------------------------
# Each import registers tools via @tool() decorator on import.
# Tier controls which modules load; profile controls which get MCP schemas.

from core.tiers import get_tier, tier_permits, tier_name, get_permitted_modules

_loaded_modules: list[str] = []

# Map of module name -> import path
_MODULE_IMPORTS = {
    "memory":       "elara_mcp.tools.memory",
    "mood":         "elara_mcp.tools.mood",
    "episodes":     "elara_mcp.tools.episodes",
    "goals":        "elara_mcp.tools.goals",
    "awareness":    "elara_mcp.tools.awareness",
    "dreams":       "elara_mcp.tools.dreams",
    "cognitive":    "elara_mcp.tools.cognitive",
    "cognition_3d": "elara_mcp.tools.cognition_3d",
    "workflows":    "elara_mcp.tools.workflows",
    "business":     "elara_mcp.tools.business",
    "llm":          "elara_mcp.tools.llm",
    "gmail":        "elara_mcp.tools.gmail",
    "knowledge":    "elara_mcp.tools.knowledge",
    "maintenance":  "elara_mcp.tools.maintenance",
    "network":      "elara_mcp.tools.network",
}

import importlib

for _mod_name, _import_path in _MODULE_IMPORTS.items():
    if tier_permits(_mod_name):
        try:
            importlib.import_module(_import_path)
            _loaded_modules.append(_mod_name)
        except Exception as _e:
            logger.warning("Failed to load module %s: %s", _mod_name, _e)

_tier = get_tier()
logger.info(
    "Tier %d (%s) — %d modules loaded: %s",
    _tier, tier_name(), len(_loaded_modules), ", ".join(_loaded_modules) or "none",
)
# Also print to stderr for CLI visibility
print(
    f"Tier {_tier} ({tier_name()}) — {len(_loaded_modules)} modules active",
    file=_sys.stderr,
)

# In lean mode, register the elara_do meta-tool for dispatching
if get_profile() == "lean" and _loaded_modules:
    import elara_mcp.tools.meta

# Initialize Layer 1 bridge (optional — silent if not installed)
_bridge_instance = None
try:
    from core.layer1_bridge import setup as setup_bridge, get_bridge
    setup_bridge()
    _bridge_instance = get_bridge()
except Exception:
    pass

# Initialize Cognitive Continuity Chain (requires bridge, tier >= 1)
_chain_instance = None
if _bridge_instance is not None and _tier >= 1:
    try:
        from daemon.events import bus as _event_bus
        from core.paths import get_paths as _get_paths
        from core.continuity import setup_chain
        _chain_instance = setup_chain(_get_paths(), _bridge_instance, _event_bus)
        if _chain_instance:
            logger.info("Continuity chain active — %d checkpoints", _chain_instance._chain_count)
    except Exception as _e:
        logger.warning("Continuity chain not started: %s", _e)


# ---------------------------------------------------------------------------
# Cortical Execution Model — initialization
# ---------------------------------------------------------------------------

def _init_cortical():
    """Initialize all cortical layers."""

    # Layer 0 — REFLEX: Cache + event-driven invalidation
    from daemon.cache import cache, setup_cache_invalidation
    setup_cache_invalidation(cache)
    logger.info("Layer 0 (REFLEX): Cache initialized")

    # Layer 1 — REACTIVE: Async event processors
    from daemon.reactive import setup_reactive_processors
    n_subs = setup_reactive_processors()
    logger.info("Layer 1 (REACTIVE): %d processors initialized", n_subs)

    # Layer 2 — DELIBERATIVE: Worker pools
    from daemon.workers import init_workers
    wm = init_workers()
    logger.info(
        "Layer 2 (DELIBERATIVE): Workers initialized (io=%d, llm=%d)",
        wm.io.max_workers, wm.llm.max_workers,
    )

    # Layer 3 — CONTEMPLATIVE: Brain events are wired through events.py
    # (Brain scheduler runs independently, emits BRAIN_THINKING_* events)
    logger.info("Layer 3 (CONTEMPLATIVE): Brain events wired")

    # Layer 4 — SOCIAL: Network uses existing async infrastructure
    logger.info("Layer 4 (SOCIAL): Network ready")

    logger.info("Cortical Execution Model: all 5 layers initialized")


def _shutdown_cortical():
    """Graceful shutdown of all cortical layers."""
    from daemon.workers import shutdown_workers
    shutdown_workers()
    shutdown_executor()
    logger.info("Cortical Execution Model: shutdown complete")


# Initialize cortical layers
_init_cortical()

# Register shutdown handler
atexit.register(_shutdown_cortical)


if __name__ == "__main__":
    mcp.run()
