"""Goals and corrections tools."""

from typing import Optional
from elara_mcp._app import mcp
from daemon.goals import (
    add_goal, update_goal, list_goals,
    boot_summary as goals_boot_summary,
)
from daemon.corrections import (
    add_correction, list_corrections, boot_corrections,
    check_corrections, record_activation,
)


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


@mcp.tool()
def elara_correction_add(
    mistake: str,
    correction: str,
    context: Optional[str] = None,
    correction_type: str = "tendency",
    fails_when: Optional[str] = None,
    fine_when: Optional[str] = None,
) -> str:
    """
    Record a correction - something I got wrong that I shouldn't repeat.

    These never decay. They load at boot so I remember.

    Args:
        mistake: What I said/did wrong
        correction: What's actually correct
        context: When/why this happened (optional)
        correction_type: "tendency" (behavioral habit) or "technical" (code/task pattern)
        fails_when: When does this mistake actually apply? (avoids overgeneralization)
        fine_when: When is this pattern actually correct? (prevents false warnings)

    Returns:
        Confirmation
    """
    entry = add_correction(
        mistake=mistake,
        correction=correction,
        context=context,
        correction_type=correction_type,
        fails_when=fails_when,
        fine_when=fine_when,
    )
    type_label = "tendency" if correction_type == "tendency" else "technical"
    return f"Correction #{entry['id']} saved [{type_label}]. Won't repeat: {mistake}"


@mcp.tool()
def elara_check_corrections(task: str) -> str:
    """
    Check if any past corrections are relevant to the current task.

    Semantic search — matches corrections by meaning, not keywords.
    Returns corrections with their conditions (fails_when/fine_when)
    so I can decide whether to heed or ignore the warning.

    Use this before starting work that might repeat a past mistake.

    Args:
        task: Description of what I'm about to do

    Returns:
        Relevant corrections with context, or "all clear"
    """
    matches = check_corrections(task)

    if not matches:
        return "No relevant corrections found. Proceed."

    lines = [f"[Corrections Check] {len(matches)} relevant:"]
    for m in matches:
        lines.append(f"  #{m['id']} ({m.get('relevance', '?')}) {m['mistake']}")
        lines.append(f"    → {m['correction']}")
        if m.get("fails_when"):
            lines.append(f"    fails when: {m['fails_when']}")
        if m.get("fine_when"):
            lines.append(f"    fine when: {m['fine_when']}")

        # Record activation
        record_activation(m["id"], was_relevant=True)

    return "\n".join(lines)


@mcp.tool()
def elara_correction_list(n: int = 20) -> str:
    """
    List recent corrections.

    Args:
        n: How many to show (default 20)

    Returns:
        List of corrections with dates and v2 metadata
    """
    corrections = list_corrections(n=n)
    if not corrections:
        return "No corrections recorded yet."

    lines = []
    for c in corrections:
        date = c["date"][:10]
        ctype = c.get("correction_type", "tendency")
        surfaced = c.get("times_surfaced", 0)
        line = f"  [{date}] #{c['id']} ({ctype}) {c['mistake']} → {c['correction']}"
        if surfaced > 0:
            line += f" [surfaced {surfaced}x]"
        lines.append(line)

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
