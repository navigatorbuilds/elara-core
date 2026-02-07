"""
Elara Dream Mode — Monthly dream.

Big picture: what shipped, what stalled, time allocation, weekly trends.
Also runs narrative threading and monthly emotional dream.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List

from daemon.schemas import atomic_write_json

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status, _is_late,
    _gather_episodes, _gather_goals, _gather_mood_journal,
    WEEKLY_DIR, MONTHLY_DIR,
)
from daemon.dream_weekly import _analyze_session_patterns, _analyze_mood_trends
from daemon.dream_threads import narrative_threads


logger = logging.getLogger("elara.dream_monthly")

def monthly_dream() -> dict:
    """Monthly big picture analysis."""
    _ensure_dirs()

    now = datetime.now()
    month_id = now.strftime("%Y-%m")

    episodes = _gather_episodes(days=30)
    goals = _gather_goals()
    mood_journal = _gather_mood_journal(days=30)

    weekly_reports = _load_weekly_reports(days=30)
    threads_result = narrative_threads()
    threads = threads_result.get("threads", [])

    # Time allocation
    project_time = {}
    for ep in episodes:
        for proj in ep.get("projects", []):
            project_time[proj] = project_time.get(proj, 0) + (ep.get("duration_minutes") or 0)

    total_time = sum(project_time.values())
    time_allocation = {}
    if total_time > 0:
        time_allocation = {
            proj: {"minutes": mins, "percent": round(mins / total_time * 100)}
            for proj, mins in sorted(project_time.items(), key=lambda x: x[1], reverse=True)
        }

    session_stats = _analyze_session_patterns(episodes)
    mood_trends = _analyze_mood_trends(mood_journal)

    shipped = []
    for g in goals.get("done_recently", []):
        shipped.append({"type": "goal_completed", "title": g["title"], "project": g.get("project")})
    for ep in episodes:
        for m in ep.get("milestones", []):
            if m.get("type") == "completion" and m.get("importance", 0) >= 0.7:
                shipped.append({"type": "milestone", "event": m["event"]})

    stalled = [
        {"title": g["title"], "project": g.get("project"),
         "days_stale": (now - datetime.fromisoformat(g["last_touched"])).days}
        for g in goals.get("stale", [])
    ]

    thread_summary = {
        "total": len(threads),
        "active": len([t for t in threads if t["status"] == "active"]),
        "stalled": len([t for t in threads if t["status"] == "stalled"]),
        "abandoned": len([t for t in threads if t["status"] == "abandoned"]),
        "threads": [
            {"name": t["name"], "status": t["status"], "episodes": t["episode_count"], "minutes": t["total_minutes"]}
            for t in threads[:15]
        ],
    }

    weekly_trends = _analyze_weekly_trends(weekly_reports)

    report = {
        "id": month_id, "type": "monthly", "generated": now.isoformat(),
        "period": {"start": (now - timedelta(days=30)).isoformat()[:10], "end": now.isoformat()[:10]},
        "episodes_analyzed": len(episodes),
        "time_allocation": time_allocation,
        "session_patterns": session_stats,
        "mood_trends": mood_trends,
        "shipped": shipped, "stalled": stalled,
        "goal_state": {"active": len(goals["active"]), "stale": len(goals["stale"]), "completed": len(goals["done_recently"])},
        "narrative_threads": thread_summary,
        "weekly_trends": weekly_trends,
        "summary": _generate_monthly_summary(
            time_allocation, session_stats, mood_trends, shipped,
            stalled, thread_summary, weekly_trends, len(episodes)
        ),
    }

    # Run monthly emotional dream alongside
    try:
        from daemon.dream_emotional import monthly_emotional_dream
        monthly_emo = monthly_emotional_dream()
        report["emotional"] = {
            "id": monthly_emo.get("id"),
            "dominant_trajectory": monthly_emo.get("dominant_trajectory"),
            "temperament_drift": monthly_emo.get("temperament_evolution", {}).get("total_drift", {}),
        }
    except Exception as e:
        report["emotional"] = {"error": str(e)}

    filepath = MONTHLY_DIR / f"{month_id}.json"
    atomic_write_json(filepath, report)
    latest = MONTHLY_DIR / "latest.json"
    atomic_write_json(latest, report)

    status = _load_status()
    status["last_monthly"] = now.isoformat()
    status["monthly_count"] = status.get("monthly_count", 0) + 1
    _save_status(status)

    return report


def _load_weekly_reports(days: int = 30) -> List[dict]:
    reports = []
    if not WEEKLY_DIR.exists():
        return reports
    cutoff = datetime.now() - timedelta(days=days)
    for f in sorted(WEEKLY_DIR.glob("*.json")):
        if f.name == "latest.json":
            continue
        try:
            report = json.loads(f.read_text())
            generated = datetime.fromisoformat(report.get("generated", ""))
            if generated >= cutoff:
                reports.append(report)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return reports


def _analyze_weekly_trends(weekly_reports: List[dict]) -> dict:
    if len(weekly_reports) < 2:
        return {"message": "Need 2+ weekly reports for trend analysis.", "weeks": len(weekly_reports)}

    session_counts = [r.get("episodes_analyzed", 0) for r in weekly_reports]
    session_trend = "increasing" if session_counts[-1] > session_counts[0] else "decreasing" if session_counts[-1] < session_counts[0] else "stable"

    total_times = [r.get("session_patterns", {}).get("total_minutes", 0) for r in weekly_reports]
    time_trend = "increasing" if total_times[-1] > total_times[0] else "decreasing" if total_times[-1] < total_times[0] else "stable"

    mood_vals = [r.get("mood_trends", {}).get("avg_valence", 0.5) for r in weekly_reports]
    mood_trend = "improving" if mood_vals[-1] > mood_vals[0] + 0.05 else "declining" if mood_vals[-1] < mood_vals[0] - 0.05 else "stable"

    return {
        "weeks_compared": len(weekly_reports),
        "session_trend": session_trend, "time_trend": time_trend, "mood_trend": mood_trend,
        "session_counts": session_counts, "total_times": total_times,
    }


def _generate_monthly_summary(
    time_alloc: dict, sessions: dict, mood: dict, shipped: list,
    stalled: list, threads: dict, weekly_trends: dict, episode_count: int,
) -> str:
    parts = []

    total = sessions.get("total_sessions", 0)
    total_min = sessions.get("total_minutes", 0)
    hours = round(total_min / 60, 1)
    parts.append(f"{total} sessions, {hours} hours this month.")

    if time_alloc:
        top_projects = list(time_alloc.items())[:3]
        alloc_strs = [f"{proj} ({info['percent']}%)" for proj, info in top_projects]
        parts.append(f"Time allocation: {', '.join(alloc_strs)}.")

    if shipped:
        parts.append(f"Shipped: {len(shipped)} items.")
        for s in shipped[:3]:
            parts.append(f"  - {s.get('title') or s.get('event')}")

    if stalled:
        stalled_names = [s["title"] for s in stalled[:3]]
        parts.append(f"Stalled: {', '.join(stalled_names)}.")

    if threads.get("total", 0) > 0:
        parts.append(f"Story arcs: {threads['active']} active, {threads['stalled']} stalled, {threads['abandoned']} abandoned.")

    types = sessions.get("type_breakdown", {})
    if types:
        items = [f"{t}: {p}%" for t, p in types.items()]
        parts.append(f"Session balance: {', '.join(items)}.")

    if mood.get("entries", 0) > 0:
        parts.append(f"Mood: valence {mood.get('valence_trend', 'stable')}, energy {mood.get('energy_trend', 'stable')}. Late night ratio: {int(mood.get('late_night_ratio', 0) * 100)}%.")

    if weekly_trends.get("weeks_compared", 0) >= 2:
        parts.append(f"Weekly trends: sessions {weekly_trends['session_trend']}, time {weekly_trends['time_trend']}, mood {weekly_trends['mood_trend']}.")

    return " ".join(parts)
