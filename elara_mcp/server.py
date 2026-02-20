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

from elara_mcp._app import mcp, get_profile, set_profile, shutdown_executor

logger = logging.getLogger("elara.server")

# Allow profile override via env var (used by MCP stdio config).
# Must happen before tool module imports — @tool() reads the profile.
_env_profile = _os.environ.get("ELARA_PROFILE")
if _env_profile and _env_profile != get_profile():
    set_profile(_env_profile)

# Import tool modules — each registers its tools via @tool() on import
import elara_mcp.tools.memory
import elara_mcp.tools.mood
import elara_mcp.tools.episodes
import elara_mcp.tools.goals
import elara_mcp.tools.awareness
import elara_mcp.tools.dreams
import elara_mcp.tools.cognitive
import elara_mcp.tools.cognition_3d
import elara_mcp.tools.workflows
import elara_mcp.tools.business
import elara_mcp.tools.llm
import elara_mcp.tools.gmail
import elara_mcp.tools.knowledge
import elara_mcp.tools.maintenance
import elara_mcp.tools.network

# In lean mode, register the elara_do meta-tool for dispatching
if get_profile() == "lean":
    import elara_mcp.tools.meta

# Initialize Layer 1 bridge (optional — silent if not installed)
try:
    from core.layer1_bridge import setup as setup_bridge
    setup_bridge()
except Exception:
    pass


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
