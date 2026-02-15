# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Episode lifecycle, notes, queries, and context tools.

Consolidated from 12 → 5 tools.
"""

from typing import Optional
from elara_mcp._app import tool
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


@tool()
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


@tool()
def elara_episode_note(
    event: str,
    note_type: str = "milestone",
    importance: float = 0.5,
    project: Optional[str] = None,
    why: Optional[str] = None,
    confidence: str = "medium",
) -> str:
    """
    Record a milestone or decision in the current episode.

    Milestones: significant events (task completed, problem solved, insight gained).
    Decisions: choices that affect future work (architecture, priorities, process).

    Args:
        event: Description of what happened or was decided
        note_type: "milestone", "decision", "insight", or "error"
        importance: 0-1, affects recall priority (0.7+ = key moment)
        project: Project this relates to (auto-added to episode)
        why: Reasoning behind decisions (used when note_type="decision")
        confidence: For decisions: "low", "medium", or "high"

    Returns:
        Confirmation of note recorded
    """
    current = get_current_episode()
    if not current:
        return "No active episode. Start one with elara_episode_start."

    episodic = get_episodic()

    if project:
        add_project_to_session(project)
        episodic.add_project(current["id"], project)

    if note_type == "decision":
        decision = episodic.add_decision(
            episode_id=current["id"],
            what=event,
            why=why,
            confidence=confidence,
            project=project
        )
        if "error" in decision:
            return f"Error: {decision['error']}"
        return f"Decision recorded ({confidence} confidence): {event}"

    # milestone, insight, error — all go through add_milestone
    milestone = episodic.add_milestone(
        episode_id=current["id"],
        event=event,
        milestone_type=note_type,
        importance=importance,
        metadata={"project": project} if project else None
    )

    if "error" in milestone:
        return f"Error: {milestone['error']}"

    importance_label = "key" if importance >= 0.7 else "normal"
    return f"{note_type.capitalize()} recorded ({importance_label}): {event}"


@tool()
def elara_episode_end(
    summary: Optional[str] = None,
    was_meaningful: bool = False
) -> str:
    """
    End the current episode.

    Finalizes the episode record with summary and mood trajectory.
    Meaningful sessions create stronger emotional imprints that persist.

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


@tool()
def elara_episode_query(
    query: Optional[str] = None,
    project: Optional[str] = None,
    n: int = 5,
    session_type: Optional[str] = None,
    current: bool = False,
    stats: bool = False,
) -> str:
    """
    Query episodes — current status, search history, or stats.

    Multi-purpose episode lookup:
    - current=True → get active episode status
    - stats=True → episodic memory statistics
    - query="..." → semantic search through milestones
    - project="..." → project history and narrative
    - No special flags → list recent episodes

    Args:
        query: Search milestones by meaning (semantic search)
        project: Filter by or get history for a project
        n: Number of results (default 5)
        session_type: Filter by "work", "drift", or "mixed"
        current: If True, show current active episode
        stats: If True, show episodic memory statistics

    Returns:
        Requested episode information
    """
    episodic = get_episodic()

    # Current episode status
    if current:
        ep = get_current_episode()
        if not ep:
            return "No active episode. Start one with elara_episode_start."

        episode = episodic.get_episode(ep["id"])
        if not episode:
            return f"Episode {ep['id']} active but not yet recorded in episodic memory."

        return (
            f"Current episode: {episode['id']}\n"
            f"Type: {episode['type']}\n"
            f"Duration: {ep['duration_minutes']} minutes\n"
            f"Projects: {', '.join(episode['projects']) or 'none'}\n"
            f"Milestones so far: {len(episode.get('milestones', []))}\n"
            f"Decisions so far: {len(episode.get('decisions', []))}"
        )

    # Stats
    if stats:
        s = episodic.get_stats()
        return (
            f"Episodic Memory Stats:\n"
            f"Total episodes: {s['total_episodes']}\n"
            f"Projects tracked: {s['projects_tracked']}\n"
            f"Projects: {', '.join(s['projects']) or 'none'}\n"
            f"Searchable milestones: {s['milestone_count']}\n"
            f"Last episode: {s['last_episode'] or 'none'}"
        )

    # Semantic search through milestones
    if query:
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

    # Project-specific narrative
    if project and not query:
        return episodic.get_project_narrative(project)

    # Default: list recent episodes
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


@tool()
def elara_context(
    topic: Optional[str] = None,
    note: Optional[str] = None,
    toggle: Optional[bool] = None,
) -> str:
    """
    Quick context for session continuity.

    Call with topic/note to save context (what we're working on).
    Call with no args to get current context.
    Call with toggle=True/False to enable/disable tracking.

    Args:
        topic: What we're working on (e.g., "building context system")
        note: Brief note about current state
        toggle: True to enable, False to disable context tracking

    Returns:
        Context info or confirmation
    """
    # Toggle
    if toggle is not None:
        context_set_enabled(toggle)
        state = "ON" if toggle else "OFF"
        return f"Context tracking: {state}"

    # Set context
    if topic or note:
        if not context_enabled():
            return "Context tracking is disabled. Call with toggle=True to enable."
        save_context(topic=topic, last_exchange=note)
        return f"Context saved: {topic or 'no topic'}"

    # Get context (default)
    if not context_enabled():
        return "Context tracking is disabled."

    ctx = get_context()
    from daemon.context import get_gap_description
    gap = get_gap_description()
    t = ctx.get("topic") or "none"
    last = ctx.get("last_exchange") or "none"

    return f"Gap: {gap}\nTopic: {t}\nLast: {last}"
