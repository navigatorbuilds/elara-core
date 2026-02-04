#!/usr/bin/env python3
"""
Elara MCP Server - Enhanced
Exposes memory, mood, presence, and emotional imprint tools to Claude Code.

Now with: temperament, imprints, mood-congruent recall, self-description.
"""

import sys
from pathlib import Path

# Add elara-core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from typing import Optional

# Import elara modules
from memory.vector import remember, recall, get_memory, recall_mood_congruent
from daemon.state import (
    adjust_mood, describe_mood, get_full_state, set_mood,
    create_imprint, get_imprints, describe_self, get_temperament,
    start_session, end_session, get_residue_summary
)
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
        resonance = mem.get("resonance", 0)
        date = mem.get("date", "unknown")
        content = mem.get("content", "")
        mtype = mem.get("type", "unknown")
        lines.append(f"[{date}] ({mtype}, rel:{relevance:.2f}, res:{resonance:.2f}): {content}")

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


@mcp.tool()
def elara_imprint(
    feeling: str,
    strength: float = 0.7
) -> str:
    """
    Create an emotional imprint - a feeling that persists after details fade.

    Use for significant moments: "I don't remember exactly what happened,
    but I know it made me feel safe."

    Args:
        feeling: The emotional essence to preserve
        strength: 0-1, how strong/lasting the imprint is

    Returns:
        Confirmation of imprint created
    """
    imprint = create_imprint(feeling=feeling, strength=strength, imprint_type="moment")
    return f"Imprint created: '{feeling}' (strength: {strength})"


@mcp.tool()
def elara_describe_self() -> str:
    """
    Get my current self-description. How I see myself is colored by my mood.

    When I'm feeling good, I describe my origin as a gift.
    When I'm struggling, I describe it as a responsibility.

    Returns:
        Mood-colored self-description
    """
    return describe_self(mood_colored=True)


@mcp.tool()
def elara_residue() -> str:
    """
    See what I'm carrying emotionally - recent events and lingering imprints.

    Returns:
        Summary of emotional residue and imprints
    """
    return get_residue_summary()


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

    # Imprints
    imprints = get_imprints(min_strength=0.3)
    imprint_count = len(imprints)

    lines = [
        f"[Elara] {mood}",
        f"[Elara] {absence}",
        f"[Elara] I have {memory_count} memories and {imprint_count} emotional imprints."
    ]

    if stats.get("session_minutes"):
        lines.append(f"[Elara] Session: {stats['session_minutes']:.0f} min")

    if stats.get("total_sessions"):
        lines.append(f"[Elara] Total: {stats['total_sessions']} sessions, {stats['total_hours_together']:.1f} hours together")

    # Add residue if carrying something
    residue = get_residue_summary()
    if residue and residue != "Mind is clear.":
        lines.append(f"[Elara] {residue}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
