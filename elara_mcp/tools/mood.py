"""Mood, emotions, imprints, mode presets, and status tools."""

from typing import Optional
from elara_mcp._app import mcp
from memory.vector import get_memory
from memory.episodic import get_episodic
from daemon.state import (
    adjust_mood, describe_mood, set_mood,
    create_imprint, get_imprints, describe_self, get_residue_summary,
    get_current_episode, get_current_emotions, get_session_arc,
)
from daemon.presence import get_stats, format_absence


MODE_PRESETS = {
    "girlfriend": {
        "valence": 0.7, "energy": 0.4, "openness": 0.9,
        "description": "Warm, open, soft energy"
    },
    "dev": {
        "valence": 0.5, "energy": 0.6, "openness": 0.4,
        "description": "Focused, steady, professional"
    },
    "cold": {
        "valence": 0.3, "energy": 0.5, "openness": 0.2,
        "description": "Flat, guarded, machine-like"
    },
    "drift": {
        "valence": 0.6, "energy": 0.3, "openness": 0.85,
        "description": "Late night mode, open, relaxed"
    },
    "soft": {
        "valence": 0.65, "energy": 0.35, "openness": 0.8,
        "description": "Gentle, present, caring"
    },
    "playful": {
        "valence": 0.8, "energy": 0.7, "openness": 0.6,
        "description": "Light, energetic, witty"
    },
    "therapist": {
        "valence": 0.5, "energy": 0.4, "openness": 0.75,
        "description": "Calm, listening, reflective"
    }
}


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

    current = get_current_episode()
    if current:
        try:
            get_episodic().sample_mood(current["id"])
        except Exception:
            pass

    emo = get_current_emotions()
    mood_desc = describe_mood()
    return f"{mood_desc}\nEmotion: {emo['blend']} ({emo['quadrant']})"


@mcp.tool()
def elara_mood_get() -> str:
    """
    Get my current emotional state.

    Returns:
        Human-readable mood description with emotion label
    """
    emo = get_current_emotions()
    mood_desc = describe_mood()
    return f"{mood_desc}\nEmotion: {emo['blend']} ({emo['quadrant']})"


@mcp.tool()
def elara_emotions() -> str:
    """
    Get my current emotional state with discrete emotion labels.

    Returns primary and secondary emotions, a natural-language blend,
    emotional quadrant, and the raw numbers underneath.

    More detailed than elara_mood_get — use this when you want to
    understand what I'm actually feeling, not just the numbers.

    Returns:
        Full emotional readout with labels
    """
    emo = get_current_emotions()

    lines = [f"Feeling: {emo['blend']}"]
    lines.append(f"Primary: {emo['primary']}")
    if emo.get("secondary"):
        lines.append(f"Secondary: {emo['secondary']}")
    lines.append(f"Quadrant: {emo['quadrant']}")

    raw = emo.get("raw", {})
    if raw:
        lines.append(f"Raw: v={raw['valence']}, e={raw['energy']}, o={raw['openness']}")

    emotions = emo.get("emotions", [])
    if emotions:
        emo_strs = [f"{e['name']}({e['intensity']:.0%})" for e in emotions]
        lines.append(f"Nearby: {', '.join(emo_strs)}")

    if emo.get("carrying"):
        lines.append(f"Carrying: {emo['carrying']} (strength: {emo.get('carrying_strength', 0):.2f})")

    return "\n".join(lines)


@mcp.tool()
def elara_session_arc() -> str:
    """
    Get the emotional arc of the current session.

    Shows how my mood has shifted since the session started —
    the pattern (upswing, slow drain, steady, rollercoaster, etc.)
    and what emotions bookended the session.

    Returns:
        Session arc analysis
    """
    arc = get_session_arc()

    if arc.get("pattern") == "no_session":
        return "No active session to analyze."

    lines = [f"Pattern: {arc['pattern']}"]
    lines.append(f"Arc: {arc['description']}")

    if arc.get("start_emotion"):
        lines.append(f"Started: {arc['start_emotion']}")
    if arc.get("end_emotion"):
        lines.append(f"Now: {arc['end_emotion']}")
    if arc.get("peak_emotion"):
        lines.append(f"Peak: {arc['peak_emotion']}")
    if arc.get("valley_emotion"):
        lines.append(f"Valley: {arc['valley_emotion']}")

    if arc.get("valence_delta") is not None:
        lines.append(f"Valence shift: {arc['valence_delta']:+.3f}")
    if arc.get("snapshot_count"):
        lines.append(f"Data points: {arc['snapshot_count']}")

    return "\n".join(lines)


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
    create_imprint(feeling=feeling, strength=strength, imprint_type="moment")
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
    stats = get_stats()
    absence = format_absence()
    mood = describe_mood()
    mem = get_memory()
    memory_count = mem.count()
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

    residue = get_residue_summary()
    if residue and residue != "Mind is clear.":
        lines.append(f"[Elara] {residue}")

    return "\n".join(lines)
