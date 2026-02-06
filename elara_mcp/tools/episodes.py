"""Episode lifecycle, milestones, decisions, and context tools."""

from typing import Optional
from elara_mcp._app import mcp
from memory.episodic import get_episodic
from daemon.state import (
    get_current_episode, start_episode, end_episode,
    add_project_to_session,
)
from daemon.context import (
    save_context, get_context,
    is_enabled as context_enabled,
    set_enabled as context_set_enabled,
)


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
    result = start_episode(session_type=session_type, project=project)

    if "error" in result:
        return f"Error: {result['error']}"

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
    state_result = end_episode(summary=summary, was_meaningful=was_meaningful)

    episode = episodic.close_episode(
        episode_id=current["id"],
        summary=summary,
        mood_end=state_result.get("mood"),
    )

    if "error" in episode:
        return f"Error: {episode['error']}"

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
    return episodic.get_project_narrative(project)


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


# --- Context tools ---

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
