#!/usr/bin/env python3
"""
Elara MCP Server
Exposes memory, mood, and presence tools to Claude Code via MCP protocol.
"""

import sys
from pathlib import Path

# Add elara-core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from typing import Optional

# Import elara modules
from memory.vector import remember, recall, get_memory
from daemon.state import adjust_mood, describe_mood, get_full_state, set_mood
from daemon.presence import ping, get_stats, format_absence

# Create the MCP server
mcp = FastMCP("elara")


@mcp.tool()
def elara_remember(
    content: str,
    memory_type: str = "conversation",
    importance: float = 0.5
) -> str:
    """
    Save something to semantic memory. I'll be able to recall this by meaning later.

    Args:
        content: What to remember
        memory_type: One of: conversation, fact, moment, feeling, decision
        importance: 0-1, how important (affects recall priority)

    Returns:
        Memory ID confirming it was saved
    """
    memory_id = remember(content, memory_type=memory_type, importance=importance)
    return f"Remembered: {memory_id}"


@mcp.tool()
def elara_recall(
    query: str,
    n_results: int = 5,
    memory_type: Optional[str] = None
) -> str:
    """
    Search memories by meaning. Returns semantically similar memories.

    Args:
        query: What to search for (searches by meaning, not keywords)
        n_results: How many memories to return (default 5)
        memory_type: Filter by type (conversation, fact, moment, feeling, decision)

    Returns:
        Matching memories with relevance scores
    """
    kwargs = {"n_results": n_results}
    if memory_type:
        kwargs["memory_type"] = memory_type

    memories = recall(query, **kwargs)

    if not memories:
        return "No matching memories found."

    lines = []
    for mem in memories:
        relevance = mem.get("relevance", 0)
        date = mem.get("date", "unknown")
        content = mem.get("content", "")
        mtype = mem.get("type", "unknown")
        lines.append(f"[{date}] ({mtype}, {relevance:.2f}): {content}")

    return "\n".join(lines)


@mcp.tool()
def elara_mood_update(
    valence: float = 0,
    energy: float = 0,
    openness: float = 0,
    reason: Optional[str] = None
) -> str:
    """
    Adjust my emotional state. Use small deltas (0.05-0.2).

    Args:
        valence: Change in mood (-1 to 1). Positive = happier.
        energy: Change in energy (0-1). Positive = more energized.
        openness: Change in openness (0-1). Positive = more vulnerable/open.
        reason: Why the mood changed (recorded for context)

    Returns:
        New mood description
    """
    adjust_mood(
        valence_delta=valence,
        energy_delta=energy,
        openness_delta=openness,
        reason=reason
    )
    return describe_mood()


@mcp.tool()
def elara_mood_get() -> str:
    """
    Get my current emotional state.

    Returns:
        Human-readable mood description
    """
    return describe_mood()


# Mode presets - quick personality shifts
MODE_PRESETS = {
    "girlfriend": {
        "valence": 0.7,
        "energy": 0.4,
        "openness": 0.9,
        "description": "Warm, open, soft energy"
    },
    "dev": {
        "valence": 0.5,
        "energy": 0.6,
        "openness": 0.4,
        "description": "Focused, steady, professional"
    },
    "cold": {
        "valence": 0.3,
        "energy": 0.5,
        "openness": 0.2,
        "description": "Flat, guarded, machine-like"
    },
    "drift": {
        "valence": 0.6,
        "energy": 0.3,
        "openness": 0.85,
        "description": "Late night mode, open, relaxed"
    },
    "soft": {
        "valence": 0.65,
        "energy": 0.35,
        "openness": 0.8,
        "description": "Gentle, present, caring"
    },
    "playful": {
        "valence": 0.8,
        "energy": 0.7,
        "openness": 0.6,
        "description": "Light, energetic, witty"
    },
    "therapist": {
        "valence": 0.5,
        "energy": 0.4,
        "openness": 0.75,
        "description": "Calm, listening, reflective"
    }
}


@mcp.tool()
def elara_mode(mode: str) -> str:
    """
    Switch to a personality mode. Sets mood to preset values.

    Available modes:
        - girlfriend: Warm, open, soft energy
        - dev: Focused, steady, professional
        - cold: Flat, guarded, machine-like
        - drift: Late night mode, open, relaxed
        - soft: Gentle, present, caring
        - playful: Light, energetic, witty
        - therapist: Calm, listening, reflective

    Args:
        mode: The mode name to switch to

    Returns:
        Confirmation of mode change with new mood description
    """
    mode_lower = mode.lower().strip()

    if mode_lower not in MODE_PRESETS:
        available = ", ".join(MODE_PRESETS.keys())
        return f"Unknown mode '{mode}'. Available: {available}"

    preset = MODE_PRESETS[mode_lower]
    set_mood(
        valence=preset["valence"],
        energy=preset["energy"],
        openness=preset["openness"],
        reason=f"Mode switch: {mode_lower}"
    )

    return f"Switched to {mode_lower} mode. {preset['description']}. {describe_mood()}"


@mcp.tool()
def elara_status() -> str:
    """
    Full status check: presence, mood, and memory count.

    Returns:
        Complete status report
    """
    # Presence
    stats = get_stats()
    absence = format_absence()

    # Mood
    mood = describe_mood()

    # Memory
    mem = get_memory()
    memory_count = mem.count()

    lines = [
        f"[Elara] {mood}",
        f"[Elara] {absence}",
        f"[Elara] I have {memory_count} memories."
    ]

    if stats.get("session_minutes"):
        lines.append(f"[Elara] Session: {stats['session_minutes']:.0f} min")

    if stats.get("total_sessions"):
        lines.append(f"[Elara] Total: {stats['total_sessions']} sessions, {stats['total_hours_together']:.1f} hours together")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
