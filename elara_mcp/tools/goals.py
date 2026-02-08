# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Goals, corrections, and session handoff tools.

Consolidated from 8 → 4 tools + 1 handoff tool.
"""

import json
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
from daemon.handoff import (
    save_handoff, load_handoff, get_carry_forward,
)


@mcp.tool()
def elara_goal(
    action: str = "list",
    title: Optional[str] = None,
    goal_id: Optional[int] = None,
    status: Optional[str] = None,
    project: Optional[str] = None,
    notes: Optional[str] = None,
    priority: str = "medium",
) -> str:
    """
    Manage goals — add, update, or list.

    Args:
        action: "add" to create, "update" to modify, "list" to view
        title: Goal title (required for add, optional for update)
        goal_id: Goal ID number (required for update)
        status: Filter for list, or new status for update ("active", "stalled", "done", "dropped")
        project: Project filter/association
        notes: Additional context
        priority: "high", "medium", or "low"

    Returns:
        Goal info or list
    """
    if action == "add":
        if not title:
            return "Error: title is required for adding a goal."
        goal = add_goal(title=title, project=project, notes=notes, priority=priority)
        return f"Goal #{goal['id']} added: {title} [{priority}]"

    if action == "update":
        if goal_id is None:
            return "Error: goal_id is required for updating a goal."
        result = update_goal(goal_id=goal_id, status=status, notes=notes, priority=priority, title=title)
        if "error" in result:
            return result["error"]
        return f"Goal #{goal_id} updated -> {result['status']}: {result['title']}"

    # list (default)
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
def elara_correction(
    action: str = "check",
    task: Optional[str] = None,
    mistake: Optional[str] = None,
    correction: Optional[str] = None,
    context: Optional[str] = None,
    correction_type: str = "tendency",
    fails_when: Optional[str] = None,
    fine_when: Optional[str] = None,
    n: int = 20,
) -> str:
    """
    Manage corrections — add, check relevance, or list.

    Corrections are mistakes I shouldn't repeat. They never decay and load at boot.

    Args:
        action: "add" to record, "check" to find relevant ones, "list" to view all
        task: What I'm about to do (required for check — semantic search)
        mistake: What I said/did wrong (required for add)
        correction: What's actually correct (required for add)
        context: When/why this happened (for add)
        correction_type: "tendency" (behavioral) or "technical" (code/task pattern)
        fails_when: When does this mistake apply? (avoids overgeneralization)
        fine_when: When is this pattern correct? (prevents false warnings)
        n: How many to show for list (default 20)

    Returns:
        Correction info, matches, or list
    """
    if action == "add":
        if not mistake or not correction:
            return "Error: 'mistake' and 'correction' are required for adding."
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

    if action == "check":
        if not task:
            return "Error: 'task' is required for checking corrections."
        matches = check_corrections(task)
        if not matches:
            return "No relevant corrections found. Proceed."

        lines = [f"[Corrections Check] {len(matches)} relevant:"]
        for m in matches:
            lines.append(f"  #{m['id']} ({m.get('relevance', '?')}) {m['mistake']}")
            lines.append(f"    -> {m['correction']}")
            if m.get("fails_when"):
                lines.append(f"    fails when: {m['fails_when']}")
            if m.get("fine_when"):
                lines.append(f"    fine when: {m['fine_when']}")
            record_activation(m["id"], was_relevant=True)

        return "\n".join(lines)

    # list (default)
    corrections = list_corrections(n=n)
    if not corrections:
        return "No corrections recorded yet."

    lines = []
    for c in corrections:
        date = c["date"][:10]
        ctype = c.get("correction_type", "tendency")
        surfaced = c.get("times_surfaced", 0)
        line = f"  [{date}] #{c['id']} ({ctype}) {c['mistake']} -> {c['correction']}"
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


@mcp.tool()
def elara_handoff(
    action: str = "save",
    session_number: int = 0,
    next_plans: str = "[]",
    reminders: str = "[]",
    promises: str = "[]",
    unfinished: str = "[]",
    mood_and_mode: str = "",
) -> str:
    """
    Session handoff — save or read between-session memory.

    This replaces freeform handoff writes. Code validates the schema,
    archives previous handoff, and writes atomically.

    Args:
        action: "save" to write handoff, "read" to see previous, "carry" to get items needing carry-forward
        session_number: Current session number (required for save)
        next_plans: JSON array of plans. Each: {"text": "...", "carried": 0, "first_seen": "ISO"}
        reminders: JSON array of reminders. Same format as plans.
        promises: JSON array of promises. Same format as plans.
        unfinished: JSON array of unfinished items. Same format as plans.
        mood_and_mode: Free-text mood/context summary for the session

    Returns:
        Success/error message, or previous handoff data
    """
    if action == "read":
        previous = load_handoff()
        if not previous:
            return "No previous handoff found."

        lines = [f"[Previous Handoff — Session {previous.get('session_number', '?')}]"]
        lines.append(f"Timestamp: {previous.get('timestamp', '?')}")
        lines.append(f"Mood: {previous.get('mood_and_mode', 'none')}")

        for field in ("next_plans", "reminders", "promises", "unfinished"):
            items = previous.get(field, [])
            if items:
                lines.append(f"\n{field.replace('_', ' ').title()} ({len(items)}):")
                for item in items:
                    carried = item.get("carried", 0)
                    tag = f" [carried {carried}x]" if carried > 0 else ""
                    lines.append(f"  - {item.get('text', '?')}{tag}")

        return "\n".join(lines)

    if action == "carry":
        carry = get_carry_forward()
        if not carry["items_to_carry"]:
            return "No items to carry forward (no previous handoff or all items fulfilled)."

        lines = [f"[Carry Forward from Session {carry['previous_session']}]"]
        if carry["mood"]:
            lines.append(f"Last mood: {carry['mood'][:100]}")

        for item in carry["items_to_carry"]:
            overdue = " ** OVERDUE **" if item["carried"] >= 3 else ""
            lines.append(f"  [{item['source']}] {item['text']} (carried {item['carried']}x){overdue}")

        return "\n".join(lines)

    # save (default)
    if session_number <= 0:
        return "Error: session_number must be positive for save."

    # Parse JSON arrays
    try:
        plans_list = json.loads(next_plans)
        reminders_list = json.loads(reminders)
        promises_list = json.loads(promises)
        unfinished_list = json.loads(unfinished)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in list parameter: {e}"

    from datetime import datetime
    data = {
        "timestamp": datetime.now().isoformat(),
        "session_number": session_number,
        "next_plans": plans_list,
        "reminders": reminders_list,
        "mood_and_mode": mood_and_mode,
        "promises": promises_list,
        "unfinished": unfinished_list,
    }

    result = save_handoff(data)
    if result["ok"]:
        total = len(plans_list) + len(reminders_list) + len(promises_list) + len(unfinished_list)
        return f"Handoff saved (session {session_number}, {total} items). Archived previous. Path: {result['path']}"
    else:
        return f"Handoff validation failed:\n" + "\n".join(f"  - {e}" for e in result["errors"])
