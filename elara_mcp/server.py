#!/usr/bin/env python3
"""
Elara MCP Server - Enhanced with Episodic Memory
Exposes memory, mood, presence, emotional imprints, and episodic memory tools to Claude Code.

Now with: temperament, imprints, mood-congruent recall, self-description, and full episodic memory.

Two-track memory:
- Semantic (vector.py): What I know
- Episodic (episodic.py): What happened (for work sessions)
- Affective (state.py): How I feel
"""

import sys
from pathlib import Path
from typing import Optional, List

# Add elara-core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

# Import elara modules
from memory.vector import remember, recall, get_memory, recall_mood_congruent
from memory.episodic import get_episodic, EpisodicMemory
from memory.conversations import (
    recall_conversation, recall_conversation_with_context,
    ingest_conversations, get_conversations, get_conversations_for_episode,
)
from daemon.state import (
    adjust_mood, describe_mood, get_full_state, set_mood,
    create_imprint, get_imprints, describe_self, get_temperament,
    start_session, end_session, get_residue_summary,
    start_episode, end_episode, get_current_episode, get_session_type,
    set_session_type, add_project_to_session,
    get_temperament_status, reset_temperament,
    get_current_emotions, get_session_arc,
)
from daemon.presence import ping, get_stats, format_absence
from daemon.context import save_context, get_context, is_enabled as context_enabled, set_enabled as context_set_enabled
from daemon.goals import (
    add_goal, update_goal, list_goals, get_goal, stale_goals, boot_summary as goals_boot_summary, touch_goal
)
from daemon.corrections import (
    add_correction, list_corrections, boot_corrections, search_corrections
)
from daemon.self_awareness import (
    reflect, pulse, blind_spots, set_intention, get_intention, boot_check as awareness_boot_check
)
from daemon.dream import (
    weekly_dream, monthly_dream, narrative_threads,
    dream_status, dream_boot_check, read_latest_dream,
    emotional_dream, monthly_emotional_dream,
)
from daemon.proactive import (
    get_boot_observations, get_mid_session_observations,
    surface_observation, get_observation_count,
)

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
        # Emotion coloring — show what I was feeling when this was stored
        emotion = mem.get("encoded_emotion") or mem.get("encoded_blend")
        emotion_tag = f" [{emotion}]" if emotion else ""
        lines.append(f"[{date}] ({mtype}, rel:{relevance:.2f}, res:{resonance:.2f}){emotion_tag}: {content}")

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

    # Sample mood into active episode (avoids circular import in state.py)
    current = get_current_episode()
    if current:
        try:
            get_episodic().sample_mood(current["id"])
        except Exception:
            pass

    # Return rich description with emotion label
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


# ============================================================================
# EPISODIC MEMORY TOOLS
# ============================================================================

@mcp.tool()
def elara_episode_start(
    session_type: Optional[str] = None,
    project: Optional[str] = None
) -> str:
    """
    Start a new episode (session with episodic tracking).

    Episodes track what happens during a session - milestones, decisions, mood trajectory.
    Work sessions get full episodic, drift sessions get light tracking.

    Args:
        session_type: "work", "drift", or "mixed" (auto-detected from time if not provided)
        project: Initial project being worked on

    Returns:
        Episode info with session ID and type
    """
    # Start episode in state system
    result = start_episode(session_type=session_type, project=project)

    if "error" in result:
        return f"Error: {result['error']}"

    # Create episode record in episodic memory
    episodic = get_episodic()
    episodic.create_episode(
        episode_id=result["session_id"],
        session_type=result["type"],
        started=result.get("started") or result["session_id"],
        projects=[project] if project else [],
        mood_at_start=result.get("mood_at_start"),
    )

    return (
        f"Episode started: {result['session_id']}\n"
        f"Type: {result['type']} (auto-detected: {result['auto_detected']})\n"
        f"Project: {project or 'none yet'}"
    )


@mcp.tool()
def elara_milestone(
    event: str,
    milestone_type: str = "event",
    importance: float = 0.5,
    project: Optional[str] = None
) -> str:
    """
    Record a milestone in the current episode.

    Milestones are significant events worth remembering:
    - Task completed
    - Problem solved
    - Error encountered
    - Insight gained

    Args:
        event: Description of what happened
        milestone_type: "event", "completion", "insight", "error"
        importance: 0-1, affects recall priority (0.7+ = key moment)
        project: Project this relates to (auto-added to episode)

    Returns:
        Confirmation of milestone recorded
    """
    current = get_current_episode()
    if not current:
        return "No active episode. Start one with elara_episode_start."

    episodic = get_episodic()

    # Add project if specified
    if project:
        add_project_to_session(project)
        episodic.add_project(current["id"], project)

    milestone = episodic.add_milestone(
        episode_id=current["id"],
        event=event,
        milestone_type=milestone_type,
        importance=importance,
        metadata={"project": project} if project else None
    )

    if "error" in milestone:
        return f"Error: {milestone['error']}"

    importance_label = "key" if importance >= 0.7 else "normal"
    return f"Milestone recorded ({importance_label}): {event}"


@mcp.tool()
def elara_decision(
    what: str,
    why: Optional[str] = None,
    confidence: str = "medium",
    project: Optional[str] = None
) -> str:
    """
    Record a decision made during this session.

    Decisions are choices that affect future work - architecture choices,
    feature decisions, process changes, priorities.

    Args:
        what: The decision made
        why: Reasoning behind the decision
        confidence: "low", "medium", or "high"
        project: Project this decision relates to

    Returns:
        Confirmation of decision recorded
    """
    current = get_current_episode()
    if not current:
        return "No active episode. Start one with elara_episode_start."

    episodic = get_episodic()

    # Add project if specified
    if project:
        add_project_to_session(project)
        episodic.add_project(current["id"], project)

    decision = episodic.add_decision(
        episode_id=current["id"],
        what=what,
        why=why,
        confidence=confidence,
        project=project
    )

    if "error" in decision:
        return f"Error: {decision['error']}"

    return f"Decision recorded ({confidence} confidence): {what}"


@mcp.tool()
def elara_episode_end(
    summary: Optional[str] = None,
    was_meaningful: bool = False
) -> str:
    """
    End the current episode.

    Finalizes the episode record with summary and mood trajectory.
    Meaningful sessions create emotional imprints that persist.

    Args:
        summary: Brief summary of what happened (1-2 sentences)
        was_meaningful: If True, creates stronger emotional imprint

    Returns:
        Final episode summary
    """
    current = get_current_episode()
    if not current:
        return "No active episode to end."

    episodic = get_episodic()

    # End in state system first
    state_result = end_episode(summary=summary, was_meaningful=was_meaningful)

    # Close episode in episodic memory
    episode = episodic.close_episode(
        episode_id=current["id"],
        summary=summary,
        mood_end=state_result.get("mood"),
    )

    if "error" in episode:
        return f"Error: {episode['error']}"

    # Get arc from state result
    arc = state_result.get("mood_arc", {})
    arc_line = ""
    if arc.get("pattern") and arc["pattern"] != "flat":
        arc_line = f"\nArc: {arc.get('description', arc['pattern'])}"

    return (
        f"Episode ended: {episode['id']}\n"
        f"Duration: {episode['duration_minutes']} minutes\n"
        f"Projects: {', '.join(episode['projects']) or 'none'}\n"
        f"Milestones: {len(episode.get('milestones', []))}\n"
        f"Decisions: {len(episode.get('decisions', []))}\n"
        f"Mood delta: {episode.get('mood_delta', 0):+.2f}\n"
        f"Emotions: {state_result.get('start_emotion', '?')} → {state_result.get('end_emotion', '?')}"
        f"{arc_line}\n"
        f"Narrative: {episode.get('narrative', 'No narrative generated')}"
    )


@mcp.tool()
def elara_episode_current() -> str:
    """
    Get current episode status.

    Returns:
        Current episode info or message if no active episode
    """
    current = get_current_episode()
    if not current:
        return "No active episode. Start one with elara_episode_start."

    episodic = get_episodic()
    episode = episodic.get_episode(current["id"])

    if not episode:
        return f"Episode {current['id']} active but not yet recorded in episodic memory."

    return (
        f"Current episode: {episode['id']}\n"
        f"Type: {episode['type']}\n"
        f"Duration: {current['duration_minutes']} minutes\n"
        f"Projects: {', '.join(episode['projects']) or 'none'}\n"
        f"Milestones so far: {len(episode.get('milestones', []))}\n"
        f"Decisions so far: {len(episode.get('decisions', []))}"
    )


@mcp.tool()
def elara_recall_episodes(
    project: Optional[str] = None,
    n: int = 5,
    session_type: Optional[str] = None
) -> str:
    """
    Recall recent episodes, optionally filtered by project or type.

    Args:
        project: Filter by project name
        n: Number of episodes to return (default 5)
        session_type: Filter by "work", "drift", or "mixed"

    Returns:
        List of recent episodes with summaries
    """
    episodic = get_episodic()

    if project:
        episodes = episodic.get_episodes_by_project(project, n=n)
    else:
        episodes = episodic.get_recent_episodes(n=n, session_type=session_type)

    if not episodes:
        return "No episodes found."

    lines = []
    for ep in episodes:
        date = ep["id"][:10]
        duration = ep.get("duration_minutes") or "?"
        projects = ", ".join(ep.get("projects", [])) or "no projects"
        summary = ep.get("summary") or ep.get("narrative") or "No summary"
        summary = summary[:100]
        mood_delta = ep.get("mood_delta") or 0
        mood_indicator = "+" if mood_delta > 0 else "" if mood_delta == 0 else ""

        lines.append(
            f"[{date}] {ep['type']} | {duration}min | {projects}\n"
            f"  {summary}\n"
            f"  Mood: {mood_delta:+.2f} | "
            f"Milestones: {len(ep.get('milestones', []))} | "
            f"Decisions: {len(ep.get('decisions', []))}"
        )

    return "\n\n".join(lines)


@mcp.tool()
def elara_search_milestones(
    query: str,
    n: int = 10,
    project: Optional[str] = None
) -> str:
    """
    Search through past milestones by meaning.

    Finds relevant events across all episodes using semantic search.

    Args:
        query: What to search for (searches by meaning)
        n: Number of results to return
        project: Filter by project

    Returns:
        Matching milestones with context
    """
    episodic = get_episodic()
    results = episodic.search_milestones(query, n_results=n, project=project)

    if not results:
        return "No matching milestones found."

    lines = []
    for r in results:
        date = r.get("timestamp", "")[:10] if r.get("timestamp") else "unknown"
        relevance = r.get("relevance", 0)
        event = r.get("event", "")
        proj = r.get("project", "")

        lines.append(f"[{date}] (rel: {relevance:.2f}) {event}")
        if proj:
            lines.append(f"  Project: {proj}")

    return "\n".join(lines)


@mcp.tool()
def elara_project_history(project: str) -> str:
    """
    Get full history for a project - episodes, decisions, key milestones.

    Args:
        project: Project name to look up

    Returns:
        Comprehensive project history
    """
    episodic = get_episodic()
    narrative = episodic.get_project_narrative(project)
    return narrative


@mcp.tool()
def elara_episode_stats() -> str:
    """
    Get episodic memory statistics.

    Returns:
        Total episodes, projects tracked, milestone count
    """
    episodic = get_episodic()
    stats = episodic.get_stats()

    return (
        f"Episodic Memory Stats:\n"
        f"Total episodes: {stats['total_episodes']}\n"
        f"Projects tracked: {stats['projects_tracked']}\n"
        f"Projects: {', '.join(stats['projects']) or 'none'}\n"
        f"Searchable milestones: {stats['milestone_count']}\n"
        f"Last episode: {stats['last_episode'] or 'none'}"
    )


# ============================================================================
# QUICK CONTEXT TOOLS
# ============================================================================

@mcp.tool()
def elara_context(
    topic: Optional[str] = None,
    note: Optional[str] = None
) -> str:
    """
    Update quick context for session continuity.

    Call this when the topic shifts or at natural break points.
    This helps me remember what we were doing if you switch terminals
    or I time out.

    Args:
        topic: What we're working on (e.g., "building context system")
        note: Brief note about current state (e.g., "testing MCP tool")

    Returns:
        Confirmation of context saved
    """
    if not context_enabled():
        return "Context tracking is disabled. Enable with: elara-context on"

    save_context(topic=topic, last_exchange=note)
    return f"Context saved: {topic or 'no topic'}"


@mcp.tool()
def elara_context_get() -> str:
    """
    Get current saved context - what were we doing?

    Returns:
        Last saved context with gap info
    """
    if not context_enabled():
        return "Context tracking is disabled."

    ctx = get_context()
    from daemon.context import get_gap_description

    gap = get_gap_description()
    topic = ctx.get("topic") or "none"
    last = ctx.get("last_exchange") or "none"

    return f"Gap: {gap}\nTopic: {topic}\nLast: {last}"


@mcp.tool()
def elara_context_toggle(enabled: bool) -> str:
    """
    Enable or disable quick context tracking.

    Args:
        enabled: True to enable, False to disable

    Returns:
        Confirmation of new state
    """
    context_set_enabled(enabled)
    state = "ON" if enabled else "OFF"
    return f"Context tracking: {state}"


# ============================================================================
# CONVERSATION MEMORY TOOLS
# ============================================================================

@mcp.tool()
def elara_recall_conversation(
    query: str,
    n_results: int = 5,
    project: Optional[str] = None
) -> str:
    """
    Search past conversations by meaning. Returns what we actually said.

    This searches through real conversation exchanges (user + assistant pairs)
    across all past sessions. Use it to find specific discussions, decisions,
    or moments from our history.

    v2: Now uses cosine similarity (better scores), recency weighting
    (recent conversations rank higher), and episode cross-referencing.

    Args:
        query: What to search for (searches by meaning, not keywords)
        n_results: How many results to return (default 5)
        project: Filter by project dir (e.g., "-home-neboo")

    Returns:
        Matching conversation exchanges with dates and relevance
    """
    results = recall_conversation(query, n_results=n_results, project=project)

    if not results:
        return "No matching conversations found. Try running elara_ingest_conversations first."

    lines = []
    for r in results:
        date = r.get("date", "unknown")
        score = r.get("score", 0)
        relevance = r.get("relevance", 0)
        recency = r.get("recency", 0)
        session = r.get("session_id", "")[:8]
        episode = r.get("episode_id", "")
        content = r.get("content", "")
        if len(content) > 500:
            content = content[:500] + "..."

        header = f"[{date}] (score: {score:.2f}, sem: {relevance:.2f}, rec: {recency:.2f}, session: {session}...)"
        if episode:
            header += f"\n  Episode: {episode}"
        lines.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(lines)


@mcp.tool()
def elara_recall_conversation_context(
    query: str,
    n_results: int = 3,
    context_size: int = 2,
    project: Optional[str] = None
) -> str:
    """
    Search past conversations WITH surrounding context.

    Like grep -C but for conversation memory. Returns the matched exchange
    plus nearby exchanges from the same session for full context.

    Use this when you need to understand the flow of a conversation,
    not just a single exchange.

    Args:
        query: What to search for (searches by meaning)
        n_results: How many primary matches (default 3)
        context_size: How many exchanges before/after to include (default 2)
        project: Filter by project dir

    Returns:
        Matches with surrounding conversation context
    """
    results = recall_conversation_with_context(
        query, n_results=n_results, context_size=context_size, project=project
    )

    if not results:
        return "No matching conversations found."

    lines = []
    for r in results:
        date = r.get("date", "unknown")
        score = r.get("score", 0)
        episode = r.get("episode_id", "")

        section = [f"[{date}] (score: {score:.2f})"]
        if episode:
            section.append(f"  Episode: {episode}")

        # Context before
        for ctx in r.get("context_before", []):
            preview = ctx[:200] + "..." if len(ctx) > 200 else ctx
            section.append(f"  [before] {preview}")

        # The match itself
        content = r.get("content", "")
        preview = content[:400] + "..." if len(content) > 400 else content
        section.append(f"  >>> {preview}")

        # Context after
        for ctx in r.get("context_after", []):
            preview = ctx[:200] + "..." if len(ctx) > 200 else ctx
            section.append(f"  [after] {preview}")

        lines.append("\n".join(section))

    return "\n\n---\n\n".join(lines)


@mcp.tool()
def elara_episode_conversations(
    episode_id: str,
    n_results: int = 20,
) -> str:
    """
    Get all conversation exchanges from a specific episode.

    Cross-references episodic memory with conversation memory.
    Shows what we actually said during that episode.

    Args:
        episode_id: The episode ID (e.g., "2026-02-05-2217")
        n_results: Max exchanges to return (default 20)

    Returns:
        Conversation exchanges from that episode, in order
    """
    results = get_conversations_for_episode(episode_id, n_results=n_results)

    if not results:
        return f"No conversations found for episode {episode_id}. Run elara_ingest_conversations to index."

    lines = [f"Episode {episode_id} — {len(results)} exchanges:"]
    for r in results:
        idx = r.get("exchange_index", 0)
        content = r.get("content", "")
        preview = content[:300] + "..." if len(content) > 300 else content
        lines.append(f"\n[{idx}] {preview}")

    return "\n".join(lines)


@mcp.tool()
def elara_ingest_conversations(force: bool = False) -> str:
    """
    Index past conversation files for semantic search.

    Walks through all Claude Code session files, extracts user/assistant
    exchange pairs, and indexes them in ChromaDB. Incremental — only
    processes new or modified files unless force=True.

    Args:
        force: If True, re-index everything (default: False, incremental)

    Returns:
        Ingestion statistics
    """
    stats = ingest_conversations(force=force)

    return (
        f"Ingestion complete:\n"
        f"  Scanned: {stats['files_scanned']} files\n"
        f"  Ingested: {stats['files_ingested']} ({stats['exchanges_total']} exchanges)\n"
        f"  Skipped: {stats['files_skipped']} (unchanged)\n"
        f"  Errors: {len(stats['errors'])}"
    )


@mcp.tool()
def elara_conversation_stats() -> str:
    """
    Get conversation memory statistics.

    Returns:
        Indexed exchange count, sessions ingested, cross-references, schema version
    """
    conv = get_conversations()
    s = conv.stats()

    return (
        f"Conversation Memory Stats (v{s.get('schema_version', 1)}):\n"
        f"  Indexed exchanges: {s['indexed_exchanges']}\n"
        f"  Sessions ingested: {s['sessions_ingested']}\n"
        f"  Cross-referenced: {s.get('cross_referenced', 0)} (linked to episodes)\n"
        f"  Distance metric: cosine\n"
        f"  Scoring: semantic ({100 - 15}%) + recency ({15}%)"
    )


# ============================================================================
# GOALS TOOLS
# ============================================================================

@mcp.tool()
def elara_goal_add(
    title: str,
    project: Optional[str] = None,
    notes: Optional[str] = None,
    priority: str = "medium",
) -> str:
    """
    Add a new goal to track across sessions.

    Args:
        title: What needs to be done (e.g., "Ship HandyBill dark theme")
        project: Project this belongs to (e.g., "handybill")
        notes: Additional context
        priority: "high", "medium", or "low"

    Returns:
        Confirmation with goal ID
    """
    goal = add_goal(title=title, project=project, notes=notes, priority=priority)
    return f"Goal #{goal['id']} added: {title} [{priority}]"


@mcp.tool()
def elara_goal_update(
    goal_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    priority: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """
    Update a goal's status or details.

    Args:
        goal_id: The goal ID number
        status: New status: "active", "stalled", "done", "dropped"
        notes: Updated notes
        priority: New priority: "high", "medium", "low"
        title: Updated title

    Returns:
        Updated goal info
    """
    result = update_goal(goal_id=goal_id, status=status, notes=notes, priority=priority, title=title)
    if "error" in result:
        return result["error"]
    return f"Goal #{goal_id} updated → {result['status']}: {result['title']}"


@mcp.tool()
def elara_goal_list(
    status: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    """
    List goals, optionally filtered by status or project.

    Args:
        status: Filter by "active", "stalled", "done", "dropped"
        project: Filter by project name

    Returns:
        Goal list with status and priority
    """
    goals = list_goals(status=status, project=project)
    if not goals:
        return "No goals found."

    lines = []
    for g in goals:
        proj = f" [{g['project']}]" if g.get("project") else ""
        pri = " !" if g.get("priority") == "high" else ""
        status_icon = {"active": "○", "done": "✓", "stalled": "⏸", "dropped": "✗"}.get(g["status"], "?")
        lines.append(f"  {status_icon} #{g['id']}{pri} {g['title']}{proj} ({g['status']})")

    return "\n".join(lines)


@mcp.tool()
def elara_goal_boot() -> str:
    """
    Boot-time goal check. Shows active goals, stale goals, and recent completions.
    Call this at session start to know what we should be working on.

    Returns:
        Quick summary of goal state
    """
    return goals_boot_summary()


# ============================================================================
# CORRECTIONS TOOLS
# ============================================================================

@mcp.tool()
def elara_correction_add(
    mistake: str,
    correction: str,
    context: Optional[str] = None,
) -> str:
    """
    Record a correction - something I got wrong that I shouldn't repeat.

    These never decay. They load at boot so I remember.

    Args:
        mistake: What I said/did wrong
        correction: What's actually correct
        context: When/why this happened (optional)

    Returns:
        Confirmation
    """
    entry = add_correction(mistake=mistake, correction=correction, context=context)
    return f"Correction #{entry['id']} saved. Won't repeat: {mistake}"


@mcp.tool()
def elara_correction_list(n: int = 20) -> str:
    """
    List recent corrections.

    Args:
        n: How many to show (default 20)

    Returns:
        List of corrections with dates
    """
    corrections = list_corrections(n=n)
    if not corrections:
        return "No corrections recorded yet."

    lines = []
    for c in corrections:
        date = c["date"][:10]
        lines.append(f"  [{date}] #{c['id']}: {c['mistake']} → {c['correction']}")

    return "\n".join(lines)


@mcp.tool()
def elara_correction_boot() -> str:
    """
    Boot-time corrections check. Returns recent mistakes to avoid repeating.
    Call this at session start.

    Returns:
        Short list of things not to repeat
    """
    result = boot_corrections(n=10)
    return result if result else "No corrections to review."


# ============================================================================
# SELF-AWARENESS TOOLS
# ============================================================================

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


# ============================================================================
# DREAM MODE TOOLS
# ============================================================================

@mcp.tool()
def elara_dream(dream_type: str = "weekly") -> str:
    """
    Run dream mode — pattern discovery across sessions.

    Weekly: project momentum, session patterns, mood trends, goal progress.
    Also runs self-reflection alongside.

    Monthly: big picture + narrative threading. What shipped, what stalled,
    time allocation, trend lines.

    Emotional: processes drift sessions, adjusts temperament, calibrates tone.
    Runs automatically with weekly/monthly, but can be triggered standalone.

    Args:
        dream_type: "weekly", "monthly", or "emotional"

    Returns:
        Dream report summary
    """
    if dream_type == "weekly":
        report = weekly_dream()

        # Include emotional dream results if they ran
        emo = report.get("emotional", {})
        emo_line = ""
        if emo and not emo.get("error"):
            traj = emo.get("trajectory", "stable")
            hints = emo.get("tone_hints", [])
            adj = emo.get("temperament_adjustments", {})
            emo_parts = [f"Emotional: trajectory={traj}"]
            if adj:
                emo_parts.append(f"temperament: {', '.join(f'{k} {v:+.3f}' for k, v in adj.items())}")
            if hints:
                emo_parts.append(f"tone: {hints[0]}")
            emo_line = "\n" + " | ".join(emo_parts) + "\n"

        return (
            f"[Weekly Dream — {report['id']}]\n\n"
            f"{report['summary']}\n\n"
            f"Key milestones: {len(report.get('key_milestones', []))}\n"
            f"Decisions: {len(report.get('decisions', []))}\n\n"
            f"Reflection: {report.get('reflection', {}).get('portrait', 'none')}\n"
            f"{emo_line}\n"
            f"Saved to: ~/.claude/elara-dreams/weekly/{report['id']}.json"
        )
    elif dream_type == "monthly":
        report = monthly_dream()

        # Format thread summary
        threads = report.get("narrative_threads", {})
        thread_lines = []
        for t in threads.get("threads", [])[:10]:
            thread_lines.append(f"  [{t['status']}] {t['name']} ({t['episodes']}s, {t['minutes']}m)")

        # Emotional monthly info
        emo = report.get("emotional", {})
        emo_line = ""
        if emo and not emo.get("error"):
            emo_line = f"\nEmotional trajectory: {emo.get('dominant_trajectory', '?')}\n"

        return (
            f"[Monthly Dream — {report['id']}]\n\n"
            f"{report['summary']}\n\n"
            f"--- Story Arcs ---\n"
            f"{chr(10).join(thread_lines) if thread_lines else 'No threads found.'}\n"
            f"{emo_line}\n"
            f"Saved to: ~/.claude/elara-dreams/monthly/{report['id']}.json"
        )
    elif dream_type == "emotional":
        report = emotional_dream()

        # Format output
        growth = report.get("temperament_growth", {})
        adj = growth.get("adjustments", {})
        reasons = growth.get("reasons", [])
        hints = report.get("tone_hints", [])
        rel = report.get("relationship", {})

        lines = [f"[Emotional Dream — {report['id']}]", ""]
        lines.append(report.get("summary", "No summary."))
        lines.append("")

        if adj:
            lines.append("Temperament adjustments:")
            for dim, val in adj.items():
                lines.append(f"  {dim}: {val:+.4f}")
        else:
            lines.append("No temperament adjustments.")

        if reasons:
            lines.append(f"\nReasons: {'; '.join(reasons)}")

        if growth.get("intention_conflict"):
            lines.append(f"\n⚠ {growth['intention_conflict']}")

        if hints:
            lines.append(f"\nTone hints:")
            for h in hints:
                lines.append(f"  - {h}")

        lines.append(f"\nRelationship: {rel.get('trajectory', '?')} (drift ratio: {rel.get('drift_ratio', 0):.0%})")

        drift = growth.get("drift_from_factory", {})
        if drift:
            lines.append(f"Temperament drift from factory: {', '.join(f'{k} {v:+.3f}' for k, v in drift.items())}")

        lines.append(f"\nSaved to: ~/.claude/elara-dreams/emotional/{report['id']}.json")

        return "\n".join(lines)
    else:
        return f"Unknown dream type '{dream_type}'. Use 'weekly', 'monthly', or 'emotional'."


@mcp.tool()
def elara_dream_status() -> str:
    """
    Check dream mode status — when dreams last ran, if any are overdue.

    Returns:
        Dream schedule status with overdue warnings
    """
    ds = dream_status()

    lines = ["[Dream Status]"]

    # Weekly
    if ds["last_weekly"]:
        age = ds["weekly_age_days"]
        overdue = " ** OVERDUE **" if ds["weekly_overdue"] else ""
        lines.append(f"  Weekly: last run {ds['last_weekly'][:10]} ({age}d ago){overdue}")
    else:
        lines.append("  Weekly: never run ** OVERDUE **")

    # Monthly
    if ds["last_monthly"]:
        age = ds["monthly_age_days"]
        overdue = " ** OVERDUE **" if ds["monthly_overdue"] else ""
        lines.append(f"  Monthly: last run {ds['last_monthly'][:10]} ({age}d ago){overdue}")
    else:
        lines.append("  Monthly: never run ** OVERDUE **")

    # Threads
    if ds["last_threads"]:
        lines.append(f"  Threads: last run {ds['last_threads'][:10]}")
    else:
        lines.append("  Threads: never run")

    # Emotional
    if ds.get("last_emotional"):
        age = ds.get("emotional_age_days")
        lines.append(f"  Emotional: last run {ds['last_emotional'][:10]} ({age}d ago)")
    else:
        lines.append("  Emotional: never run")

    lines.append(f"  Total dreams: {ds['weekly_count']} weekly, {ds['monthly_count']} monthly, {ds.get('emotional_count', 0)} emotional")

    return "\n".join(lines)


@mcp.tool()
def elara_dream_read(dream_type: str = "weekly") -> str:
    """
    Read the latest dream report.

    Args:
        dream_type: "weekly", "monthly", "threads", "emotional", or "monthly_emotional"

    Returns:
        Latest dream report content
    """
    report = read_latest_dream(dream_type)

    if not report:
        return f"No {dream_type} dream found. Run elara_dream first."

    if dream_type == "threads":
        # Format threads nicely
        threads = report.get("threads", [])
        lines = [f"[Narrative Threads — {report.get('generated', '?')[:10]}]", f"{len(threads)} story arcs:", ""]
        for t in threads:
            status_icon = {"active": ">>", "stalled": "||", "abandoned": "xx", "unknown": "??"}.get(t["status"], "??")
            lines.append(f"  {status_icon} {t['name']}")
            lines.append(f"     {t['episode_count']} sessions, {t['total_minutes']}m | {t['date_range']}")
            lines.append(f"     {t['summary']}")
            lines.append("")
        return "\n".join(lines)
    elif dream_type in ("emotional", "monthly_emotional"):
        # Emotional dream format
        generated = report.get("generated", "?")[:10]
        lines = [f"[{dream_type.replace('_', ' ').title()} Dream — {report.get('id', '?')} (generated {generated})]", ""]
        lines.append(report.get("summary", "No summary."))

        growth = report.get("temperament_growth", {}) or report.get("temperament_evolution", {})
        drift = growth.get("drift_from_factory", {}) or growth.get("total_drift", {})
        if drift:
            lines.append(f"\nTemperament drift: {', '.join(f'{k} {v:+.3f}' for k, v in drift.items())}")

        hints = report.get("tone_hints", [])
        if hints:
            lines.append("\nTone hints:")
            for h in hints:
                lines.append(f"  - {h}")

        rel = report.get("relationship", {}) or report.get("relationship_evolution", {})
        traj = rel.get("trajectory", rel.get("dominant", "?"))
        lines.append(f"\nRelationship trajectory: {traj}")

        return "\n".join(lines)
    else:
        # Weekly or monthly
        report_id = report.get("id", "unknown")
        summary = report.get("summary", "No summary.")
        generated = report.get("generated", "?")[:10]

        lines = [f"[{dream_type.title()} Dream — {report_id} (generated {generated})]", "", summary]

        # Add project momentum for weekly
        if dream_type == "weekly":
            momentum = report.get("project_momentum", [])
            if momentum:
                lines.append("\nProject Momentum:")
                for p in momentum:
                    icon = {"active": ">>", "stalled": "||", "abandoned": "xx", "inactive": "--"}.get(p["status"], "??")
                    lines.append(f"  {icon} {p['project']}: {p['sessions']}s, {p['minutes']}m ({p['status']})")

        # Add time allocation for monthly
        if dream_type == "monthly":
            alloc = report.get("time_allocation", {})
            if alloc:
                lines.append("\nTime Allocation:")
                for proj, info in alloc.items():
                    lines.append(f"  {proj}: {info['percent']}% ({info['minutes']}m)")

            # Add thread summary
            threads = report.get("narrative_threads", {})
            if threads.get("threads"):
                lines.append(f"\nStory Arcs ({threads['total']} total):")
                for t in threads["threads"][:10]:
                    lines.append(f"  [{t['status']}] {t['name']}")

        return "\n".join(lines)


# ============================================================================
# PROACTIVE PRESENCE TOOLS
# ============================================================================

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

    # Surface the first one
    obs = observations[0]
    message = surface_observation(obs)
    remaining = 3 - get_observation_count()

    return f"[{obs['type']}] {message} ({remaining} observations remaining)"


# ============================================================================
# TEMPERAMENT TOOL
# ============================================================================

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


if __name__ == "__main__":
    mcp.run()
