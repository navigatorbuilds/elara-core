# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Goals System - Persistent goal tracking across sessions.

Storage: ~/.claude/elara-goals.json
Simple JSON, no database. Checked at boot, updated during sessions.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from core.paths import get_paths
from daemon.events import bus, Events
from daemon.schemas import Goal, load_validated_list, save_validated_list

logger = logging.getLogger("elara.goals")

GOALS_FILE = get_paths().goals_file


def _load() -> List[Dict]:
    logger.debug("Loading goals from %s", GOALS_FILE)
    models = load_validated_list(GOALS_FILE, Goal)
    return [m.model_dump() for m in models]


def _save(goals: List[Dict]):
    logger.debug("Saving %d goals to %s", len(goals), GOALS_FILE)
    models = [Goal.model_validate(g) for g in goals]
    save_validated_list(GOALS_FILE, models)


def _next_id(goals: List[Dict]) -> int:
    if not goals:
        return 1
    return max(g["id"] for g in goals) + 1


def add_goal(
    title: str,
    project: Optional[str] = None,
    notes: Optional[str] = None,
    priority: str = "medium",
    decision: Optional[str] = None,
    build_order: Optional[int] = None,
) -> Dict:
    logger.info("Adding goal: %s (priority=%s)", title, priority)
    goals = _load()
    now = datetime.now().isoformat()
    goal = Goal(
        id=_next_id(goals),
        title=title,
        project=project,
        status="active",
        priority=priority,
        created=now,
        last_touched=now,
        notes=notes,
        decision=decision,
        build_order=build_order,
    ).model_dump()
    goals.append(goal)
    _save(goals)
    bus.emit(Events.GOAL_ADDED, {
        "id": goal["id"],
        "title": title,
        "project": project,
        "priority": priority,
    }, source="goals")
    return goal


def update_goal(
    goal_id: int,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    priority: Optional[str] = None,
    title: Optional[str] = None,
    decision: Optional[str] = None,
    build_order: Optional[int] = None,
) -> Dict:
    goals = _load()
    for g in goals:
        if g["id"] == goal_id:
            changed = False
            if status:
                g["status"] = status
                changed = True
            if notes:
                g["notes"] = notes
                changed = True
            if priority:
                g["priority"] = priority
                changed = True
            if title:
                g["title"] = title
                changed = True
            if decision is not None:
                g["decision"] = decision
                changed = True
            if build_order is not None:
                g["build_order"] = build_order
                changed = True
            if not changed:
                return g
            g["last_touched"] = datetime.now().isoformat()
            _save(goals)
            bus.emit(Events.GOAL_UPDATED, {
                "id": goal_id,
                "status": g["status"],
                "title": g["title"],
            }, source="goals")
            return g
    logger.warning("Goal %d not found for update", goal_id)
    return {"error": f"Goal {goal_id} not found"}


def touch_goal(goal_id: int):
    goals = _load()
    for g in goals:
        if g["id"] == goal_id:
            g["last_touched"] = datetime.now().isoformat()
            _save(goals)
            return


def list_goals(
    status: Optional[str] = None,
    project: Optional[str] = None,
) -> List[Dict]:
    goals = _load()
    if status:
        goals = [g for g in goals if g["status"] == status]
    if project:
        goals = [g for g in goals if g.get("project") == project]
    return goals


def get_goal(goal_id: int) -> Optional[Dict]:
    goals = _load()
    for g in goals:
        if g["id"] == goal_id:
            return g
    return None


def stale_goals(days: int = 7) -> List[Dict]:
    """Find active goals not touched in N days."""
    goals = _load()
    now = datetime.now()
    stale = []
    for g in goals:
        if g["status"] != "active":
            continue
        last = datetime.fromisoformat(g["last_touched"])
        if (now - last).days >= days:
            stale.append(g)
    return stale


def boot_summary() -> str:
    """Quick summary for session boot."""
    goals = _load()
    active = [g for g in goals if g["status"] == "active"]
    stale = stale_goals(days=7)
    done_recent = [
        g for g in goals
        if g["status"] == "done"
        and (datetime.now() - datetime.fromisoformat(g["last_touched"])).days < 3
    ]

    lines = []
    if active:
        lines.append(f"Active goals ({len(active)}):")
        for g in sorted(active, key=lambda x: (x.get("build_order") or 999, {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1))):
            proj = f" [{g['project']}]" if g.get("project") else ""
            pri = f" !" if g.get("priority") == "high" else ""
            dec = f" — {g['decision'][:60]}" if g.get("decision") else ""
            lines.append(f"  #{g['id']}{pri} {g['title']}{proj}{dec}")

    if stale:
        lines.append(f"\nStale ({len(stale)} not touched in 7+ days):")
        for g in stale:
            days_ago = (datetime.now() - datetime.fromisoformat(g["last_touched"])).days
            lines.append(f"  #{g['id']} {g['title']} ({days_ago}d ago)")

    if done_recent:
        lines.append(f"\nRecently done:")
        for g in done_recent:
            lines.append(f"  #{g['id']} {g['title']} ✓")

    if not lines:
        return "No goals set."

    return "\n".join(lines)
