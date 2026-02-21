# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Tier System — hardware capability gating.

4 deployment tiers controlling which modules LOAD at runtime:

  Tier 0 — VALIDATE:  Crypto + DAG only (IoT, embedded sensors)
  Tier 1 — REMEMBER:  + memory, episodes, goals, maintenance
  Tier 2 — THINK:     + mood, awareness, dreams, cognitive, cognition_3d,
                         workflows, knowledge, business, llm, gmail (DEFAULT)
  Tier 3 — CONNECT:   + network (full mesh participation)

Tier controls which modules LOAD. Profile controls which loaded tools
get MCP schemas. They're orthogonal.

Usage:
    from core.tiers import set_tier, get_tier, tier_permits

    set_tier(1)                        # constrain to REMEMBER
    tier_permits("mood")               # False — mood needs tier 2
    get_permitted_modules()            # {"memory", "episodes", "goals", "maintenance"}
"""

import logging
import os
from typing import Optional, Set

logger = logging.getLogger("elara.tiers")

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_NAMES = {
    0: "VALIDATE",
    1: "REMEMBER",
    2: "THINK",
    3: "CONNECT",
}

TIER_DESCRIPTIONS = {
    0: "Crypto + DAG only (IoT, embedded, sensors)",
    1: "Memory, episodes, goals, maintenance ($30 phones, low-RAM)",
    2: "Full cognitive stack minus network (desktop, default)",
    3: "Everything including mesh network (full node)",
}

# Modules available at each tier (cumulative — tier N includes all of tier N-1)
_TIER_MODULES: dict[int, set[str]] = {
    0: set(),  # no tool modules — just bridge
    1: {"memory", "episodes", "goals", "maintenance"},
    2: {"memory", "episodes", "goals", "maintenance",
        "mood", "awareness", "dreams", "cognitive", "cognition_3d",
        "workflows", "knowledge", "business", "llm", "gmail", "udr"},
    3: {"memory", "episodes", "goals", "maintenance",
        "mood", "awareness", "dreams", "cognitive", "cognition_3d",
        "workflows", "knowledge", "business", "llm", "gmail", "udr",
        "network"},
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_current_tier: int = 2  # default


def _resolve_default_tier() -> int:
    """Read tier from ELARA_TIER env var if set."""
    env = os.environ.get("ELARA_TIER")
    if env is not None:
        try:
            t = int(env)
            if t in TIER_NAMES:
                return t
        except ValueError:
            pass
    return 2


_current_tier = _resolve_default_tier()

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def set_tier(tier: int) -> None:
    """Set the active deployment tier (0-3)."""
    global _current_tier
    if tier not in TIER_NAMES:
        raise ValueError(f"Invalid tier {tier}. Must be 0-3.")
    old = _current_tier
    _current_tier = tier
    if old != tier:
        logger.info("Tier changed: %d (%s) -> %d (%s)",
                     old, TIER_NAMES[old], tier, TIER_NAMES[tier])
        # Emit event (lazy import to avoid circular deps)
        try:
            from daemon.events import bus, Events
            bus.emit(Events.TIER_CHANGED, {
                "old_tier": old,
                "new_tier": tier,
                "old_name": TIER_NAMES[old],
                "new_name": TIER_NAMES[tier],
            }, source="core.tiers")
        except Exception:
            pass


def get_tier() -> int:
    """Return the current deployment tier."""
    return _current_tier


def tier_name(tier: Optional[int] = None) -> str:
    """Human-readable name for a tier. Defaults to current tier."""
    t = tier if tier is not None else _current_tier
    return TIER_NAMES.get(t, f"UNKNOWN({t})")


def tier_permits(module_name: str) -> bool:
    """Check if the current tier allows a given module to load."""
    permitted = _TIER_MODULES.get(_current_tier, set())
    return module_name in permitted


def get_permitted_modules() -> Set[str]:
    """Return the set of module names permitted at the current tier."""
    return set(_TIER_MODULES.get(_current_tier, set()))


def tier_info() -> dict:
    """Full tier status for diagnostics."""
    return {
        "current_tier": _current_tier,
        "name": TIER_NAMES[_current_tier],
        "description": TIER_DESCRIPTIONS[_current_tier],
        "permitted_modules": sorted(get_permitted_modules()),
        "module_count": len(get_permitted_modules()),
    }
