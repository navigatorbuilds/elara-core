# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Dream Mode — Weekly dream.

Project momentum, session patterns, mood trends, goal progress.
Also runs reflect() and emotional_dream alongside.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
import json

from daemon.schemas import atomic_write_json

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status, _is_late,
    _gather_episodes, _gather_goals, _gather_corrections,
    _gather_mood_journal, WEEKLY_DIR,
)


logger = logging.getLogger("elara.dream_weekly")

def weekly_dream() -> dict:
    """Weekly pattern analysis. Also runs reflect() and emotional_dream alongside."""
    _ensure_dirs()

    episodes = _gather_episodes(days=7)
    goals = _gather_goals()
    corrections = _gather_corrections()
    mood_journal = _gather_mood_journal(days=7)

    from daemon.self_awareness import reflect
    reflection = reflect()

    # Project momentum
    project_sessions = {}
    project_minutes = {}
    for ep in episodes:
        for proj in ep.get("projects", []):
            project_sessions[proj] = project_sessions.get(proj, 0) + 1
            project_minutes[proj] = project_minutes.get(proj, 0) + (ep.get("duration_minutes") or 0)

    project_momentum = []
    for proj in set(list(project_sessions.keys()) + [g.get("project") for g in goals["active"] if g.get("project")]):
        sessions = project_sessions.get(proj, 0)
        minutes = project_minutes.get(proj, 0)
        has_goal = any(g.get("project") == proj for g in goals["active"])
        is_stale = any(g.get("project") == proj for g in goals["stale"])

        status = "active" if sessions > 0 else "stalled" if has_goal else "inactive"
        if is_stale and sessions == 0:
            status = "abandoned"

        project_momentum.append({
            "project": proj, "sessions": sessions, "minutes": minutes,
            "status": status, "has_active_goal": has_goal,
        })

    session_stats = _analyze_session_patterns(episodes)
    mood_trends = _analyze_mood_trends(mood_journal)

    goal_progress = {
        "active_count": len(goals["active"]),
        "stale_count": len(goals["stale"]),
        "completed_this_period": len(goals["done_recently"]),
        "stale_goals": [
            {"id": g["id"], "title": g["title"],
             "days_stale": (datetime.now() - datetime.fromisoformat(g["last_touched"])).days}
            for g in goals["stale"]
        ],
    }

    all_milestones = []
    for ep in episodes:
        for m in ep.get("milestones", []):
            if m.get("importance", 0) >= 0.7:
                all_milestones.append({
                    "event": m["event"], "episode": ep["id"],
                    "project": ",".join(ep.get("projects", [])),
                })

    all_decisions = []
    for ep in episodes:
        for d in ep.get("decisions", []):
            all_decisions.append({
                "what": d["what"], "why": d.get("why"),
                "confidence": d.get("confidence"), "project": d.get("project"),
            })

    correction_analysis = {
        "total": len(corrections),
        "recent": corrections[-5:] if corrections else [],
    }

    now = datetime.now()
    week_num = now.isocalendar()[1]
    dream_id = f"{now.year}-W{week_num:02d}"

    report = {
        "id": dream_id, "type": "weekly", "generated": now.isoformat(),
        "period": {"start": (now - timedelta(days=7)).isoformat()[:10], "end": now.isoformat()[:10]},
        "episodes_analyzed": len(episodes),
        "project_momentum": project_momentum,
        "session_patterns": session_stats,
        "mood_trends": mood_trends,
        "goal_progress": goal_progress,
        "key_milestones": all_milestones[:10],
        "decisions": all_decisions[:10],
        "corrections": correction_analysis,
        "reflection": {"portrait": reflection.get("portrait", ""), "mood_stats": reflection.get("mood", {})},
        "summary": _generate_weekly_summary(
            project_momentum, session_stats, mood_trends, goal_progress,
            all_milestones, all_decisions, len(episodes)
        ),
    }

    filepath = WEEKLY_DIR / f"{dream_id}.json"
    atomic_write_json(filepath, report)
    latest = WEEKLY_DIR / "latest.json"
    atomic_write_json(latest, report)

    # Run emotional dream alongside
    try:
        from daemon.dream_emotional import emotional_dream
        emotional_report = emotional_dream()
        report["emotional"] = {
            "id": emotional_report.get("id"),
            "trajectory": emotional_report.get("relationship", {}).get("trajectory"),
            "tone_hints": emotional_report.get("tone_hints", []),
            "temperament_adjustments": emotional_report.get("temperament_growth", {}).get("adjustments", {}),
        }
    except Exception as e:
        report["emotional"] = {"error": str(e)}

    status = _load_status()
    status["last_weekly"] = now.isoformat()
    status["weekly_count"] = status.get("weekly_count", 0) + 1
    _save_status(status)

    return report


def _analyze_session_patterns(episodes: List[dict]) -> dict:
    """Analyze session timing and behavior patterns."""
    if not episodes:
        return {"total_sessions": 0, "message": "No sessions this period."}

    total = len(episodes)
    total_minutes = sum(ep.get("duration_minutes") or 0 for ep in episodes)

    types = {}
    for ep in episodes:
        t = ep.get("type", "mixed")
        types[t] = types.get(t, 0) + 1
    type_pct = {t: round(c / total * 100) for t, c in types.items()}

    hours = []
    for ep in episodes:
        try:
            started = datetime.fromisoformat(ep.get("started", ""))
            hours.append(started.hour)
        except (ValueError, TypeError):
            pass

    hour_buckets = {"morning (6-12)": 0, "afternoon (12-18)": 0, "evening (18-22)": 0, "late night (22-6)": 0}
    for h in hours:
        if 6 <= h < 12: hour_buckets["morning (6-12)"] += 1
        elif 12 <= h < 18: hour_buckets["afternoon (12-18)"] += 1
        elif 18 <= h < 22: hour_buckets["evening (18-22)"] += 1
        else: hour_buckets["late night (22-6)"] += 1

    days = {}
    for ep in episodes:
        try:
            started = datetime.fromisoformat(ep.get("started", ""))
            day_name = started.strftime("%A")
            days[day_name] = days.get(day_name, 0) + 1
        except (ValueError, TypeError):
            pass

    durations = [ep.get("duration_minutes") or 0 for ep in episodes if ep.get("duration_minutes")]
    avg_duration = round(sum(durations) / len(durations)) if durations else 0

    return {
        "total_sessions": total, "total_minutes": total_minutes,
        "avg_duration_min": avg_duration, "type_breakdown": type_pct,
        "time_of_day": hour_buckets, "day_of_week": days,
    }


def _analyze_mood_trends(journal: List[dict]) -> dict:
    """Analyze mood journal for trends."""
    if not journal:
        return {"entries": 0, "message": "No mood data this period."}

    valences = [e.get("v", 0.5) for e in journal]
    energies = [e.get("e", 0.5) for e in journal]

    avg_v = round(sum(valences) / len(valences), 3)
    avg_e = round(sum(energies) / len(energies), 3)

    trend_v = "stable"
    trend_e = "stable"
    if len(journal) >= 6:
        mid = len(journal) // 2
        first_v = sum(e.get("v", 0.5) for e in journal[:mid]) / mid
        second_v = sum(e.get("v", 0.5) for e in journal[mid:]) / (len(journal) - mid)
        first_e = sum(e.get("e", 0.5) for e in journal[:mid]) / mid
        second_e = sum(e.get("e", 0.5) for e in journal[mid:]) / (len(journal) - mid)

        if second_v - first_v > 0.05: trend_v = "rising"
        elif second_v - first_v < -0.05: trend_v = "falling"
        if second_e - first_e > 0.05: trend_e = "rising"
        elif second_e - first_e < -0.05: trend_e = "falling"

    late = sum(1 for e in journal if _is_late(e.get("ts", "")))
    late_ratio = round(late / len(journal), 2)

    return {
        "entries": len(journal), "avg_valence": avg_v, "avg_energy": avg_e,
        "valence_trend": trend_v, "energy_trend": trend_e, "late_night_ratio": late_ratio,
    }


def _generate_weekly_summary(
    momentum: List[dict], sessions: dict, mood: dict, goals: dict,
    milestones: List[dict], decisions: List[dict], episode_count: int,
) -> str:
    """Generate natural-language weekly summary."""
    parts = []

    total = sessions.get("total_sessions", 0)
    total_min = sessions.get("total_minutes", 0)
    avg = sessions.get("avg_duration_min", 0)
    parts.append(f"{total} sessions, {total_min} minutes total (avg {avg} min/session).")

    types = sessions.get("type_breakdown", {})
    if types:
        items = [f"{t}: {p}%" for t, p in types.items()]
        parts.append(f"Session types: {', '.join(items)}.")

    tod = sessions.get("time_of_day", {})
    most_active = max(tod, key=tod.get) if tod else None
    if most_active:
        parts.append(f"Most active: {most_active} ({tod[most_active]} sessions).")

    active_projects = [p for p in momentum if p["status"] == "active"]
    stalled_projects = [p for p in momentum if p["status"] in ("stalled", "abandoned")]
    if active_projects:
        proj_strs = [f"{p['project']} ({p['sessions']}s, {p['minutes']}m)" for p in active_projects]
        parts.append(f"Active projects: {', '.join(proj_strs)}.")
    if stalled_projects:
        proj_names = [p["project"] for p in stalled_projects]
        parts.append(f"Stalled/abandoned: {', '.join(proj_names)}.")

    if milestones:
        parts.append(f"{len(milestones)} key milestones this week.")
    if decisions:
        parts.append(f"{len(decisions)} decisions recorded.")
    if goals.get("stale_count", 0) > 0:
        parts.append(f"{goals['stale_count']} goals stale (7+ days untouched).")
    if goals.get("completed_this_period", 0) > 0:
        parts.append(f"{goals['completed_this_period']} goals completed.")

    if mood.get("entries", 0) > 0:
        parts.append(f"Mood: valence {mood.get('valence_trend', 'stable')}, energy {mood.get('energy_trend', 'stable')}. Late night ratio: {int(mood.get('late_night_ratio', 0) * 100)}%.")

    return " ".join(parts)
