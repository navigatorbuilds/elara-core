"""
Elara Self-Awareness — Blind Spots lens.

"What am I missing?" — contrarian: stale goals, repeating mistakes, avoidance.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List

from core.paths import get_paths

logger = logging.getLogger("elara.awareness.blind_spots")

BLIND_SPOTS_FILE = get_paths().blind_spots_file


def blind_spots() -> dict:
    """
    Contrarian analysis. What are we avoiding?

    Checks: stale goals, repeating corrections, abandoned projects,
    dormant corrections (never activated).
    """
    from daemon.goals import list_goals, stale_goals
    from daemon.corrections import list_corrections, get_dormant_corrections
    from memory.episodic import get_episodic

    spots = []

    # --- Stale goals ---
    stale = stale_goals(days=7)
    if stale:
        for g in stale:
            days_ago = (datetime.now() - datetime.fromisoformat(g["last_touched"])).days
            spots.append({
                "type": "stale_goal",
                "detail": f"Goal #{g['id']} '{g['title']}' untouched for {days_ago} days.",
                "severity": "high" if days_ago > 14 else "medium",
            })

    # --- Repeating corrections ---
    corrections = list_corrections(n=20)
    if len(corrections) >= 3:
        # Look for similar mistakes (simple word overlap check)
        mistakes = [c.get("mistake", "").lower() for c in corrections]
        seen_words = {}
        for m in mistakes:
            for word in m.split():
                if len(word) > 4:  # Skip small words
                    seen_words[word] = seen_words.get(word, 0) + 1
        repeated = {w: c for w, c in seen_words.items() if c >= 2}
        if repeated:
            top_word = max(repeated, key=repeated.get)
            spots.append({
                "type": "repeating_correction",
                "detail": f"The word '{top_word}' appears in {repeated[top_word]} corrections. Pattern?",
                "severity": "medium",
            })

    # --- Abandoned projects ---
    episodic = get_episodic()
    projects = episodic.index.get("by_project", {})
    for project, episode_ids in projects.items():
        if not episode_ids:
            continue
        last_ep = episodic.get_episode(episode_ids[-1])
        if last_ep and last_ep.get("ended"):
            try:
                ended = datetime.fromisoformat(last_ep["ended"])
                days_since = (datetime.now() - ended).days
                if days_since > 7:
                    spots.append({
                        "type": "abandoned_project",
                        "detail": f"Project '{project}' — last touched {days_since} days ago.",
                        "severity": "medium" if days_since < 14 else "high",
                    })
            except (ValueError, TypeError):
                pass

    # --- Dormant corrections (never activated) ---
    dormant = get_dormant_corrections(days=14)
    for d in dormant:
        if d.get("times_surfaced", 0) == 0:
            dormant_days = (datetime.now() - datetime.fromisoformat(d["date"])).days
            if dormant_days >= 3:
                spots.append({
                    "type": "dormant_correction",
                    "detail": f"Correction #{d['id']} '{d['mistake'][:50]}' has never been activated ({dormant_days}d old). Still relevant?",
                    "severity": "medium" if dormant_days < 14 else "high",
                })

    # --- Active goals without recent episodes ---
    active_goals = list_goals(status="active")
    for g in active_goals:
        proj = g.get("project")
        if proj and proj in projects:
            eps = projects[proj]
            if eps:
                last_ep = episodic.get_episode(eps[-1])
                if last_ep and last_ep.get("ended"):
                    try:
                        ended = datetime.fromisoformat(last_ep["ended"])
                        if (datetime.now() - ended).days > 7:
                            spots.append({
                                "type": "goal_no_work",
                                "detail": f"Goal '{g['title']}' is active but no work episodes in 7+ days.",
                                "severity": "high",
                            })
                    except (ValueError, TypeError):
                        pass

    # --- Recurring problem areas (from reasoning trails) ---
    try:
        from daemon.reasoning import get_recurring_problem_tags
        recurring = get_recurring_problem_tags(min_count=3)
        for r in recurring:
            spots.append({
                "type": "recurring_problem",
                "detail": f"Tag '{r['tag']}' appears in {r['count']} reasoning trails. Systemic issue?",
                "severity": "high" if r["count"] >= 5 else "medium",
            })
    except Exception:
        pass

    # --- Outcome loss patterns ---
    try:
        from daemon.outcomes import get_loss_patterns, get_unchecked_outcomes
        loss_patterns = get_loss_patterns(min_losses=2)
        for p in loss_patterns:
            spots.append({
                "type": "outcome_loss_pattern",
                "detail": f"Tag '{p['tag']}' has {p['loss_count']} losses. Overestimating this area?",
                "severity": "high" if p["loss_count"] >= 3 else "medium",
            })

        forgotten = get_unchecked_outcomes(days_old=7)
        if len(forgotten) >= 3:
            spots.append({
                "type": "forgotten_decisions",
                "detail": f"{len(forgotten)} decisions recorded but never checked (7+ days). Close the loop.",
                "severity": "medium",
            })
    except Exception:
        pass

    # --- Goal conflicts ---
    try:
        conflicts = detect_goal_conflicts(active_goals)
        spots.extend(conflicts)
    except Exception:
        pass

    result = {
        "timestamp": datetime.now().isoformat(),
        "spots": spots,
        "count": len(spots),
        "summary": _generate_blind_spots_summary(spots),
    }

    BLIND_SPOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLIND_SPOTS_FILE.write_text(json.dumps(result, indent=2))

    return result


def _generate_blind_spots_summary(spots: list) -> str:
    """Natural language blind spots summary."""
    if not spots:
        return "No blind spots detected. Either we're on track, or I can't see what I can't see."

    high = [s for s in spots if s["severity"] == "high"]
    medium = [s for s in spots if s["severity"] == "medium"]

    parts = [f"{len(spots)} blind spots found."]

    if high:
        parts.append(f"{len(high)} need attention:")
        for s in high[:3]:
            parts.append(f"  - {s['detail']}")

    if medium:
        parts.append(f"{len(medium)} worth noting:")
        for s in medium[:3]:
            parts.append(f"  - {s['detail']}")

    return "\n".join(parts)


# ============================================================================
# GOAL CONFLICT DETECTION
# ============================================================================

def detect_goal_conflicts(goals: List[dict]) -> List[dict]:
    """
    Detect conflicts between active goals.

    4 detectors:
    1. Resource conflict — multiple high-priority goals on same project
    2. Time conflict — too many active goals vs recent work sessions
    3. Staleness pattern — setting goals faster than completing them
    4. Priority inversion — high-priority stale while low-priority gets work
    """
    conflicts = []
    conflicts.extend(_check_resource_conflicts(goals))
    conflicts.extend(_check_time_conflicts(goals))
    conflicts.extend(_check_staleness_pattern(goals))
    conflicts.extend(_check_priority_inversions(goals))
    return conflicts


def _check_resource_conflicts(goals: List[dict]) -> List[dict]:
    """Multiple high-priority goals competing for the same project."""
    by_project = {}
    for g in goals:
        proj = g.get("project")
        if proj and g.get("priority") == "high":
            by_project.setdefault(proj, []).append(g)

    conflicts = []
    for proj, high_goals in by_project.items():
        if len(high_goals) >= 2:
            titles = [g["title"] for g in high_goals[:3]]
            conflicts.append({
                "type": "resource_conflict",
                "detail": f"Project '{proj}' has {len(high_goals)} high-priority goals competing: {', '.join(titles)}. Which is actually most important?",
                "severity": "high" if len(high_goals) >= 3 else "medium",
            })
    return conflicts


def _check_time_conflicts(goals: List[dict]) -> List[dict]:
    """Too many active goals relative to recent work activity."""
    if len(goals) <= 5:
        return []

    # Check recent episode count
    try:
        from memory.episodic import get_episodic
        episodic = get_episodic()
        recent = episodic.get_recent_episodes(n=10)
        recent_7d = [
            ep for ep in recent
            if ep.get("ended") and
            (datetime.now() - datetime.fromisoformat(ep["ended"])).days <= 7
        ]
        sessions_last_week = len(recent_7d)
    except Exception:
        sessions_last_week = 3  # assume moderate if we can't check

    if len(goals) > sessions_last_week * 2:
        return [{
            "type": "time_conflict",
            "detail": f"{len(goals)} active goals but only {sessions_last_week} work sessions last week. Overcommitted?",
            "severity": "high" if len(goals) > 8 else "medium",
        }]
    return []


def _check_staleness_pattern(goals: List[dict]) -> List[dict]:
    """Setting goals faster than completing them — 3+ stale = pattern."""
    stale = [g for g in goals if _is_stale(g, days=7)]
    if len(stale) >= 3:
        return [{
            "type": "staleness_pattern",
            "detail": f"{len(stale)} goals stale (7+ days). Creating goals faster than working on them.",
            "severity": "high" if len(stale) >= 5 else "medium",
        }]
    return []


def _check_priority_inversions(goals: List[dict]) -> List[dict]:
    """High-priority goals stale while low-priority goals get recent attention."""
    high_stale = [g for g in goals if g.get("priority") == "high" and _is_stale(g, days=7)]
    low_recent = [g for g in goals if g.get("priority") == "low" and not _is_stale(g, days=3)]

    conflicts = []
    for hg in high_stale:
        for lg in low_recent:
            conflicts.append({
                "type": "priority_inversion",
                "detail": f"High-priority '{hg['title']}' is stale but low-priority '{lg['title']}' got recent work. Priorities misaligned?",
                "severity": "medium",
            })
            if len(conflicts) >= 2:
                return conflicts  # cap at 2 to avoid noise
    return conflicts


def _is_stale(goal: dict, days: int) -> bool:
    """Check if a goal hasn't been touched in N days."""
    try:
        last = datetime.fromisoformat(goal["last_touched"])
        return (datetime.now() - last).days >= days
    except (ValueError, TypeError, KeyError):
        return False
