"""Self-awareness, proactive observation, and temperament tools."""

from typing import Optional
from elara_mcp._app import mcp
from daemon.self_awareness import (
    reflect, pulse, blind_spots,
    set_intention, get_intention,
    boot_check as awareness_boot_check,
)
from daemon.proactive import (
    get_boot_observations, get_mid_session_observations,
    surface_observation, get_observation_count,
)
from daemon.state import get_temperament_status, reset_temperament


@mcp.tool()
def elara_reflect() -> str:
    """
    Self-reflection: "Who have I been lately?"

    Analyzes mood journal, imprints, and corrections to generate
    a self-portrait. Shows mood trends, energy patterns, what I'm
    carrying, what I've lost.

    Run at session end or on demand. Saves to file for cheap boot reads.

    Returns:
        Self-portrait with mood analysis
    """
    result = reflect()

    portrait = result.get("portrait", "No portrait generated.")
    mood = result.get("mood", {})
    imprints = result.get("imprints", {})

    lines = ["[Self-Reflection]", ""]
    lines.append(portrait)
    lines.append("")

    if mood.get("entries", 0) > 0:
        lines.append(f"Mood data: {mood['entries']} entries")
        lines.append(f"  Valence: {mood.get('valence_avg', '?')} (trend: {mood.get('valence_trend', '?')})")
        lines.append(f"  Energy: {mood.get('energy_avg', '?')} (trend: {mood.get('energy_trend', '?')})")
        lines.append(f"  Late night ratio: {mood.get('late_night_ratio', 0):.0%}")

    if imprints.get("recently_faded"):
        lines.append(f"  Recently faded: {', '.join(imprints['recently_faded'])}")

    return "\n".join(lines)


@mcp.tool()
def elara_pulse() -> str:
    """
    Relationship pulse: "How are we doing?"

    Analyzes session frequency, drift/work balance, gap patterns,
    and mood trajectory across episodes.

    Surfaces signals like: sessions getting sparse, no drift in weeks,
    mood trending down across sessions.

    Returns:
        Relationship health summary with signals
    """
    result = pulse()

    summary = result.get("summary", "No data.")
    signals = result.get("signals", [])
    sessions = result.get("sessions", {})

    lines = ["[Relationship Pulse]", ""]
    lines.append(summary)

    if sessions.get("days_since_drift") is not None:
        lines.append(f"\nDays since drift session: {sessions['days_since_drift']}")

    if sessions.get("episode_balance"):
        balance = sessions["episode_balance"]
        items = [f"{k}: {int(v * 100)}%" for k, v in balance.items()]
        lines.append(f"Episode balance: {', '.join(items)}")

    return "\n".join(lines)


@mcp.tool()
def elara_blind_spots() -> str:
    """
    Contrarian analysis: "What am I missing?"

    Finds stale goals, repeating correction patterns, abandoned projects,
    and goals with no recent work. The echo chamber fighter.

    Returns:
        List of blind spots with severity
    """
    result = blind_spots()

    if result["count"] == 0:
        return "No blind spots detected. Either we're on track, or I can't see what I can't see."

    lines = ["[Blind Spots]", ""]
    lines.append(result["summary"])

    return "\n".join(lines)


@mcp.tool()
def elara_intention(
    what: Optional[str] = None,
) -> str:
    """
    Set or check a growth intention.

    The loop: reflect → intend → check → grow.

    Call with 'what' to set a new intention.
    Call without arguments to check current intention.

    Args:
        what: One specific thing to do differently (None = check current)

    Returns:
        Current intention and previous if exists
    """
    if what:
        result = set_intention(what, check_previous=True)

        lines = [f"Intention set: \"{what}\""]
        if result.get("previous_intention"):
            lines.append(f"Previous was: \"{result['previous_intention']}\" (set {result['previous_set_at'][:10]})")
            lines.append("Did I follow through? That's worth thinking about.")

        return "\n".join(lines)
    else:
        intention = get_intention()
        if not intention:
            return "No active intention. Run elara_reflect first, then set one."

        lines = [f"Active intention: \"{intention['what']}\""]
        lines.append(f"Set: {intention['set_at'][:10]}")

        if intention.get("previous"):
            prev = intention["previous"]
            lines.append(f"Before that: \"{prev.get('what', '?')}\"")

        return "\n".join(lines)


@mcp.tool()
def elara_awareness_boot() -> str:
    """
    Boot-time awareness check. Reads saved reflection/pulse/blind_spots
    files and surfaces anything notable. Cheap — just reads small JSONs.

    Call at session start alongside goal_boot and correction_boot.

    Returns:
        Notable observations, or nothing if all clear
    """
    result = awareness_boot_check()

    if not result:
        return "All clear. No observations from last reflection."

    return f"[Awareness] {result}"


@mcp.tool()
def elara_observe_boot() -> str:
    """
    Run proactive observations at session start.

    Checks for notable patterns: session gaps, mood trends, time patterns,
    stale goals, heavy imprints, session type balance.

    Returns observations I should naturally work into my greeting.
    Max 3 per session, pure Python (zero token cost for detection).

    Returns:
        List of observations or "nothing notable"
    """
    observations = get_boot_observations()

    if not observations:
        return "Nothing notable to surface."

    lines = [f"[Proactive] {len(observations)} observation(s):"]
    for obs in observations:
        severity_icon = {"gentle": "~", "notable": "!", "positive": "+"}.get(obs["severity"], "?")
        lines.append(f"  {severity_icon} [{obs['type']}] {obs['message']}")
        if obs.get("suggestion"):
            lines.append(f"    → {obs['suggestion']}")

    return "\n".join(lines)


@mcp.tool()
def elara_observe_now() -> str:
    """
    Check for mid-session observations.

    Call this at natural break points (topic shifts, after long tasks).
    Respects cooldown — won't fire more than 3x per session or within
    5 minutes of the last observation.

    Returns:
        Observation to surface, or "nothing to note"
    """
    observations = get_mid_session_observations()

    if not observations:
        remaining = 3 - get_observation_count()
        return f"Nothing to note right now. ({remaining} observations remaining this session)"

    obs = observations[0]
    message = surface_observation(obs)
    remaining = 3 - get_observation_count()

    return f"[{obs['type']}] {message} ({remaining} observations remaining)"


@mcp.tool()
def elara_temperament(do_reset: bool = False) -> str:
    """
    Check or reset my temperament — who I am at baseline.

    Shows current temperament vs factory defaults, drift amounts,
    and recent adjustments from emotional dreams.

    Args:
        do_reset: If True, resets temperament to factory defaults (nuclear option)

    Returns:
        Temperament status report
    """
    if do_reset:
        reset_temperament()
        return "Temperament reset to factory defaults. All learned adjustments cleared."

    status = get_temperament_status()
    current = status["current"]
    factory = status["factory"]
    drift = status["drift"]
    max_drift = status["max_allowed_drift"]
    recent = status["recent_adjustments"]

    lines = ["[Temperament Status]", ""]

    lines.append("Current vs Factory:")
    for dim in ["valence", "energy", "openness"]:
        curr = current.get(dim, 0)
        fact = factory.get(dim, 0)
        d = drift.get(dim, 0)
        marker = " *" if abs(d) > 0.05 else ""
        lines.append(f"  {dim}: {curr:.3f} (factory: {fact:.3f}, drift: {d:+.3f}){marker}")

    lines.append(f"\nMax allowed drift: +/-{max_drift}")

    if recent:
        lines.append(f"\nRecent adjustments ({len(recent)}):")
        for r in recent:
            lines.append(f"  [{r.get('ts', '?')[:10]}] {r['dim']} {r['delta']:+.4f} — {r['reason']}")

    if not drift:
        lines.append("\nAt factory baseline. No learned adjustments yet.")

    return "\n".join(lines)
