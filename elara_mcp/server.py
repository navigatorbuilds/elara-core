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
    set_session_type, add_project_to_session
)
from daemon.presence import ping, get_stats, format_absence
from daemon.context import save_context, get_context, is_enabled as context_enabled, set_enabled as context_set_enabled
from daemon.goals import (
    add_goal, update_goal, list_goals, get_goal, stale_goals, boot_summary as goals_boot_summary, touch_goal
)
from daemon.corrections import (
    add_correction, list_corrections, boot_corrections, search_corrections
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

    return (
        f"Episode ended: {episode['id']}\n"
        f"Duration: {episode['duration_minutes']} minutes\n"
        f"Projects: {', '.join(episode['projects']) or 'none'}\n"
        f"Milestones: {len(episode.get('milestones', []))}\n"
        f"Decisions: {len(episode.get('decisions', []))}\n"
        f"Mood delta: {episode.get('mood_delta', 0):+.2f}\n"
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


if __name__ == "__main__":
    mcp.run()
