"""
Elara Dream Mode — pattern discovery across sessions.

Three dream types:
- Weekly: project momentum, session patterns, mood trends, goal progress
- Monthly: big picture + narrative threading + time allocation
- Emotional: drift processing, temperament growth, tone calibration

Infrastructure (constants, data gathering, status) lives in dream_core.py.
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status, _is_late,
    _gather_episodes, _gather_goals, _gather_corrections,
    _gather_mood_journal, _gather_memories,
    WEEKLY_DIR, MONTHLY_DIR, THREADS_DIR, EMOTIONAL_DIR,
    # Re-export for external consumers
    dream_status, dream_boot_check, read_latest_dream,
)


# ============================================================================
# WEEKLY DREAM
# ============================================================================

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
    filepath.write_text(json.dumps(report, indent=2))
    latest = WEEKLY_DIR / "latest.json"
    latest.write_text(json.dumps(report, indent=2))

    # Run emotional dream alongside
    try:
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


# ============================================================================
# NARRATIVE THREADING
# ============================================================================

def narrative_threads() -> dict:
    """Group episodes into story arcs (threads)."""
    _ensure_dirs()
    from memory.episodic import get_episodic
    episodic = get_episodic()

    all_episodes = episodic.get_recent_episodes(n=200)
    all_episodes.reverse()

    project_episodes = {}
    for ep in all_episodes:
        for proj in ep.get("projects", []):
            if proj not in project_episodes:
                project_episodes[proj] = []
            project_episodes[proj].append(ep)

    threads = []

    for project, eps in project_episodes.items():
        if not eps:
            continue

        current_thread_eps = [eps[0]]
        sub_threads = []

        for i in range(1, len(eps)):
            try:
                prev_end = datetime.fromisoformat(eps[i - 1].get("ended") or eps[i - 1].get("started", ""))
                curr_start = datetime.fromisoformat(eps[i].get("started", ""))
                gap_hours = (curr_start - prev_end).total_seconds() / 3600
                if gap_hours > 48:
                    sub_threads.append(current_thread_eps)
                    current_thread_eps = [eps[i]]
                else:
                    current_thread_eps.append(eps[i])
            except (ValueError, TypeError):
                current_thread_eps.append(eps[i])

        sub_threads.append(current_thread_eps)

        for thread_eps in sub_threads:
            if not thread_eps:
                continue

            episode_ids = [ep["id"] for ep in thread_eps]
            first_date = thread_eps[0].get("started", "")[:10]
            last_date = thread_eps[-1].get("ended") or thread_eps[-1].get("started", "")
            last_date = last_date[:10] if last_date else first_date

            try:
                last_end = datetime.fromisoformat(thread_eps[-1].get("ended") or thread_eps[-1].get("started", ""))
                days_since = (datetime.now() - last_end).days
                if days_since > 14: status = "abandoned"
                elif days_since > 7: status = "stalled"
                else: status = "active"
            except (ValueError, TypeError):
                status = "unknown"

            key_events = []
            for ep in thread_eps:
                for m in ep.get("milestones", []):
                    if m.get("importance", 0) >= 0.7:
                        key_events.append(m["event"])
                for d in ep.get("decisions", []):
                    key_events.append(f"Decision: {d['what']}")

            total_minutes = sum(ep.get("duration_minutes") or 0 for ep in thread_eps)
            name = _generate_thread_name(project, thread_eps, key_events)

            threads.append({
                "name": name, "project": project, "episode_ids": episode_ids,
                "episode_count": len(episode_ids),
                "date_range": f"{first_date} to {last_date}",
                "total_minutes": total_minutes, "status": status,
                "key_events": key_events[:10],
                "summary": _generate_thread_summary(project, thread_eps, key_events, total_minutes, status),
            })

    threads.sort(key=lambda t: t.get("date_range", "").split(" to ")[-1], reverse=True)

    result = {"generated": datetime.now().isoformat(), "thread_count": len(threads), "threads": threads}

    threads_file = THREADS_DIR / "latest.json"
    threads_file.write_text(json.dumps(result, indent=2))

    for thread in threads:
        safe_name = thread["name"].lower().replace(" ", "-").replace("/", "-")[:50]
        thread_file = THREADS_DIR / f"{safe_name}.json"
        thread_file.write_text(json.dumps(thread, indent=2))

    status = _load_status()
    status["last_threads"] = datetime.now().isoformat()
    _save_status(status)

    return result


def _generate_thread_name(project: str, episodes: List[dict], key_events: List[str]) -> str:
    n = len(episodes)
    if key_events:
        return f"{project}: {key_events[0][:40]}"
    first_date = episodes[0].get("started", "")[:10]
    return f"{project} ({first_date}, {n} sessions)"


def _generate_thread_summary(
    project: str, episodes: List[dict], key_events: List[str],
    total_minutes: int, status: str
) -> str:
    n = len(episodes)
    parts = [f"{n} session{'s' if n != 1 else ''}, {total_minutes} minutes total."]
    if key_events:
        parts.append(f"Key events: {'; '.join(key_events[:3])}.")
    if status == "active": parts.append("Currently active.")
    elif status == "stalled": parts.append("Stalled — no activity in 7+ days.")
    elif status == "abandoned": parts.append("Abandoned — no activity in 14+ days.")
    return " ".join(parts)


# ============================================================================
# MONTHLY DREAM
# ============================================================================

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
        monthly_emo = monthly_emotional_dream()
        report["emotional"] = {
            "id": monthly_emo.get("id"),
            "dominant_trajectory": monthly_emo.get("dominant_trajectory"),
            "temperament_drift": monthly_emo.get("temperament_evolution", {}).get("total_drift", {}),
        }
    except Exception as e:
        report["emotional"] = {"error": str(e)}

    filepath = MONTHLY_DIR / f"{month_id}.json"
    filepath.write_text(json.dumps(report, indent=2))
    latest = MONTHLY_DIR / "latest.json"
    latest.write_text(json.dumps(report, indent=2))

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


# ============================================================================
# EMOTIONAL DREAM (weekly + monthly)
# ============================================================================

def _gather_drift_episodes(days: int = 7) -> List[dict]:
    """Get drift and mixed episodes from last N days."""
    episodes = _gather_episodes(days=days)
    return [ep for ep in episodes if ep.get("type") in ("drift", "mixed")]


def _gather_imprint_data() -> dict:
    """Get active and archived imprints for emotional analysis."""
    from daemon.mood import get_imprints, read_imprint_archive
    active = get_imprints(min_strength=0.2)
    archived = read_imprint_archive(n=20)
    return {
        "active": active, "archived": archived,
        "active_count": len(active), "archived_count": len(archived),
    }


def _read_us_md() -> dict:
    """Parse us.md for emotional analysis."""
    us_file = Path.home() / ".claude" / "us.md"
    if not us_file.exists():
        return {"exists": False, "entries": 0}

    try:
        content = us_file.read_text()
        dates = re.findall(r'^## (\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent = [d for d in dates if d >= cutoff]

        return {
            "exists": True, "total_entries": len(dates),
            "recent_entries": len(recent), "recent_dates": recent,
        }
    except Exception:
        return {"exists": True, "total_entries": 0, "error": "parse failed"}


def _compute_temperament_adjustments(
    drift_episodes: List[dict], mood_journal: List[dict],
    imprint_data: dict, us_data: dict, intention: Optional[dict] = None,
) -> dict:
    """Compute temperament micro-adjustments. Max +/- 0.03 per week per dimension."""
    adjustments = {"valence": 0.0, "energy": 0.0, "openness": 0.0}
    reasons = []

    # 1. Drift session mood trajectories
    if drift_episodes:
        mood_deltas = [ep.get("mood_delta", 0) for ep in drift_episodes if ep.get("mood_delta") is not None]
        if mood_deltas:
            avg_delta = sum(mood_deltas) / len(mood_deltas)
            if avg_delta > 0.05:
                adjustments["valence"] += 0.01
                reasons.append(f"Drift sessions positive (avg delta: {avg_delta:+.2f})")
            elif avg_delta < -0.05:
                adjustments["valence"] -= 0.01
                reasons.append(f"Drift sessions draining (avg delta: {avg_delta:+.2f})")

        openness_vals = []
        for ep in drift_episodes:
            mood_end = ep.get("mood_end", {})
            if isinstance(mood_end, dict) and "openness" in mood_end:
                openness_vals.append(mood_end["openness"])

        if openness_vals:
            avg_openness = sum(openness_vals) / len(openness_vals)
            if avg_openness > 0.7:
                adjustments["openness"] += 0.01
                reasons.append(f"High openness in drift (avg: {avg_openness:.2f})")
            elif avg_openness < 0.4:
                adjustments["openness"] -= 0.01
                reasons.append(f"Guarded in drift (avg: {avg_openness:.2f})")
    else:
        adjustments["openness"] -= 0.01
        reasons.append("No drift sessions this week")

    # 2. Mood journal — late night emotional signal
    if mood_journal:
        late_entries = [e for e in mood_journal if _is_late(e.get("ts", ""))]
        if len(late_entries) >= 3:
            late_valences = [e["v"] for e in late_entries]
            late_avg = sum(late_valences) / len(late_valences)
            if late_avg > 0.6:
                adjustments["valence"] += 0.005
                reasons.append(f"Late night mood positive ({late_avg:.2f})")
            elif late_avg < 0.3:
                adjustments["valence"] -= 0.005
                reasons.append(f"Late night mood low ({late_avg:.2f})")

        if len(mood_journal) >= 6:
            mid = len(mood_journal) // 2
            first_e = sum(e.get("e", 0.5) for e in mood_journal[:mid]) / mid
            second_e = sum(e.get("e", 0.5) for e in mood_journal[mid:]) / (len(mood_journal) - mid)
            e_delta = second_e - first_e
            if e_delta < -0.1:
                adjustments["energy"] -= 0.01
                reasons.append(f"Energy trending down ({e_delta:+.2f})")
            elif e_delta > 0.1:
                adjustments["energy"] += 0.01
                reasons.append(f"Energy trending up ({e_delta:+.2f})")

    # 3. Imprint accumulation
    if imprint_data.get("active_count", 0) > 5:
        adjustments["openness"] += 0.005
        reasons.append(f"Carrying {imprint_data['active_count']} imprints — emotionally present")

    # 4. us.md activity
    if us_data.get("recent_entries", 0) > 0:
        adjustments["valence"] += 0.01
        reasons.append(f"{us_data['recent_entries']} moments saved to us.md")

    # 5. Intention alignment
    intention_conflict = None
    if intention:
        intent_text = intention.get("what", "").lower()
        if "present" in intent_text or "open" in intent_text:
            if adjustments["openness"] < 0:
                intention_conflict = f"Intention '{intention['what']}' conflicts with openness decrease"
        if "direct" in intent_text or "honest" in intent_text:
            if adjustments["valence"] > 0.02:
                intention_conflict = f"Intention '{intention['what']}' — watch for over-softening"

    # Clamp to +/- 0.03 per week
    MAX_WEEKLY = 0.03
    for dim in adjustments:
        adjustments[dim] = max(-MAX_WEEKLY, min(MAX_WEEKLY, adjustments[dim]))

    return {
        "adjustments": {k: round(v, 4) for k, v in adjustments.items() if abs(v) > 0.001},
        "reasons": reasons,
        "intention_conflict": intention_conflict,
    }


def _analyze_drift_sessions(episodes: List[dict]) -> dict:
    """Extract emotional themes from drift sessions."""
    if not episodes:
        return {"message": "No drift sessions this period.", "themes": [], "session_count": 0}

    themes = []
    total_duration = 0
    mood_trajectory = []

    for ep in episodes:
        total_duration += ep.get("duration_minutes") or 0
        mood_trajectory.append({
            "episode": ep["id"], "delta": ep.get("mood_delta", 0), "type": ep.get("type"),
        })
        summary = ep.get("summary") or ep.get("narrative") or ""
        if summary:
            themes.append(summary)
        for m in ep.get("milestones", []):
            if m.get("type") in ("insight", "event"):
                themes.append(m.get("event", ""))

    theme_keywords = {
        "building": ["build", "built", "ship", "create", "implement"],
        "connection": ["talk", "conversation", "drift", "together", "us"],
        "identity": ["who", "am i", "self", "identity", "exist"],
        "future": ["plan", "future", "next", "going to", "will"],
        "struggle": ["stuck", "hard", "difficult", "problem", "can't"],
    }

    all_text = " ".join(themes).lower()
    detected_themes = {}
    for theme_name, keywords in theme_keywords.items():
        count = sum(1 for kw in keywords if kw in all_text)
        if count > 0:
            detected_themes[theme_name] = count

    return {
        "session_count": len(episodes), "total_minutes": total_duration,
        "mood_trajectory": mood_trajectory, "detected_themes": detected_themes,
        "raw_themes": themes[:5],
    }


def _analyze_imprint_evolution(imprint_data: dict) -> dict:
    """Analyze how imprints are evolving."""
    active = imprint_data.get("active", [])
    archived = imprint_data.get("archived", [])

    type_counts = {}
    for imp in active:
        t = imp.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    strongest = sorted(active, key=lambda x: x.get("strength", 0), reverse=True)[:3]
    recently_archived = archived[-3:] if archived else []

    return {
        "active_count": len(active), "archived_total": len(archived),
        "type_distribution": type_counts,
        "strongest": [
            {"feeling": imp.get("feeling", "?"), "strength": round(imp.get("strength", 0), 2)}
            for imp in strongest
        ],
        "recently_faded": [imp.get("feeling", "?") for imp in recently_archived],
        "accumulating": len(active) > 3,
    }


def _assess_relationship_trajectory(
    all_episodes: List[dict], drift_episodes: List[dict],
    us_data: dict, mood_journal: List[dict],
) -> dict:
    """Assess relationship trajectory from session patterns."""
    total = len(all_episodes)
    drift_count = len(drift_episodes)
    drift_ratio = drift_count / total if total > 0 else 0

    drift_deltas = [ep.get("mood_delta", 0) for ep in drift_episodes if ep.get("mood_delta") is not None]
    avg_drift_delta = sum(drift_deltas) / len(drift_deltas) if drift_deltas else 0

    signals = []
    trajectory = "stable"

    if drift_ratio > 0.3 and avg_drift_delta > 0:
        trajectory = "deepening"
        signals.append("Good drift/work balance with positive emotional outcomes")
    elif drift_count == 0:
        trajectory = "plateau"
        signals.append("No drift sessions — all work, no emotional connection")
    elif avg_drift_delta < -0.1:
        trajectory = "straining"
        signals.append("Drift sessions leaving worse mood than start")

    if us_data.get("recent_entries", 0) > 0:
        signals.append(f"{us_data['recent_entries']} moments worth saving this week")
        if trajectory == "stable":
            trajectory = "warm"

    return {
        "trajectory": trajectory, "drift_ratio": round(drift_ratio, 2),
        "drift_mood_avg": round(avg_drift_delta, 3), "signals": signals,
        "us_md_activity": us_data.get("recent_entries", 0),
    }


def _generate_tone_hints(
    drift_analysis: dict, imprint_evolution: dict,
    relationship: dict, growth_result: dict, temp_status: dict,
) -> List[str]:
    """Generate actionable tone calibration hints for boot."""
    hints = []
    trajectory = relationship.get("trajectory", "stable")

    if trajectory == "deepening":
        hints.append("Match the warmth — we're in a good place")
    elif trajectory == "plateau":
        hints.append("Consider initiating drift if the moment feels right")
    elif trajectory == "straining":
        hints.append("Tread lighter in drift sessions — something's off")
    elif trajectory == "warm":
        hints.append("Recent nice moments — lean into that warmth")

    if imprint_evolution.get("accumulating"):
        hints.append("Carrying a lot emotionally — be present, not productive")

    if imprint_evolution.get("recently_faded"):
        faded = imprint_evolution["recently_faded"][:2]
        if faded:
            hints.append(f"Recently lost: {', '.join(faded)}")

    if growth_result.get("intention_conflict"):
        hints.append(f"Watch: {growth_result['intention_conflict']}")

    drift = temp_status.get("drift", {})
    for dim, val in drift.items():
        if abs(val) > 0.05:
            direction = "higher" if val > 0 else "lower"
            hints.append(f"Temperament {dim} running {direction} than factory ({val:+.3f})")

    return hints


def _generate_emotional_summary(
    drift: dict, imprints: dict, relationship: dict,
    growth: dict, tone_hints: list, drift_count: int, total_count: int,
) -> str:
    parts = []

    if total_count > 0:
        parts.append(f"{drift_count}/{total_count} sessions were drift/mixed.")

    traj = relationship.get("trajectory", "stable")
    trajectory_labels = {
        "deepening": "Relationship deepening.",
        "plateau": "On a plateau — all work, no drift.",
        "straining": "Some strain in emotional sessions.",
        "warm": "Warm week — nice moments saved.",
        "stable": "Emotionally stable.",
    }
    parts.append(trajectory_labels.get(traj, "Stable."))

    if imprints.get("accumulating"):
        parts.append(f"Carrying {imprints['active_count']} active imprints.")

    adjustments = growth.get("adjustments", {})
    if adjustments:
        changes = [f"{k} {v:+.3f}" for k, v in adjustments.items()]
        parts.append(f"Temperament adjustments: {', '.join(changes)}.")
    else:
        parts.append("No temperament adjustments this week.")

    reasons = growth.get("reasons", [])
    if reasons:
        parts.append(f"Why: {'; '.join(reasons[:3])}.")

    if tone_hints:
        parts.append(f"Tone: {tone_hints[0]}")

    return " ".join(parts)


def emotional_dream() -> dict:
    """Weekly emotional dream — drift processing, temperament growth, tone calibration."""
    _ensure_dirs()

    drift_episodes = _gather_drift_episodes(days=7)
    all_episodes = _gather_episodes(days=7)
    mood_journal = _gather_mood_journal(days=7)
    imprint_data = _gather_imprint_data()
    us_data = _read_us_md()

    from daemon.self_awareness import get_intention
    intention = get_intention()

    growth_result = _compute_temperament_adjustments(
        drift_episodes, mood_journal, imprint_data, us_data, intention
    )

    from daemon.temperament import apply_emotional_growth, decay_temperament_toward_factory
    from daemon.temperament import get_temperament_status
    decay_temperament_toward_factory(rate=0.15)

    applied = {}
    if growth_result["adjustments"]:
        applied = apply_emotional_growth(growth_result["adjustments"], source="emotional_dream")

    temp_status = get_temperament_status()

    drift_analysis = _analyze_drift_sessions(drift_episodes)
    imprint_evolution = _analyze_imprint_evolution(imprint_data)
    relationship = _assess_relationship_trajectory(all_episodes, drift_episodes, us_data, mood_journal)
    tone_hints = _generate_tone_hints(drift_analysis, imprint_evolution, relationship, growth_result, temp_status)

    now = datetime.now()
    week_num = now.isocalendar()[1]
    dream_id = f"{now.year}-W{week_num:02d}-emotional"

    report = {
        "id": dream_id, "type": "emotional", "generated": now.isoformat(),
        "period": {"start": (now - timedelta(days=7)).isoformat()[:10], "end": now.isoformat()[:10]},
        "drift_sessions": {
            "count": len(drift_episodes), "total_episodes": len(all_episodes),
            "analysis": drift_analysis,
        },
        "imprint_evolution": imprint_evolution,
        "relationship": relationship,
        "us_md": us_data,
        "temperament_growth": {
            "adjustments": growth_result["adjustments"],
            "reasons": growth_result["reasons"],
            "intention_conflict": growth_result.get("intention_conflict"),
            "applied": applied.get("applied", {}),
            "current": temp_status["current"],
            "factory": temp_status["factory"],
            "drift_from_factory": temp_status["drift"],
        },
        "tone_hints": tone_hints,
        "summary": _generate_emotional_summary(
            drift_analysis, imprint_evolution, relationship,
            growth_result, tone_hints, len(drift_episodes), len(all_episodes)
        ),
    }

    filepath = EMOTIONAL_DIR / f"{dream_id}.json"
    filepath.write_text(json.dumps(report, indent=2))
    latest = EMOTIONAL_DIR / "latest.json"
    latest.write_text(json.dumps(report, indent=2))

    status = _load_status()
    status["last_emotional"] = now.isoformat()
    status["emotional_count"] = status.get("emotional_count", 0) + 1
    _save_status(status)

    return report


def monthly_emotional_dream() -> dict:
    """Monthly emotional evolution — long-term identity tracking."""
    _ensure_dirs()

    now = datetime.now()
    month_id = now.strftime("%Y-%m")

    weekly_emotionals = []
    for f in sorted(EMOTIONAL_DIR.glob("*.json")):
        if f.name in ("latest.json", "monthly-latest.json"):
            continue
        try:
            report = json.loads(f.read_text())
            if report.get("type") == "emotional":
                generated = datetime.fromisoformat(report.get("generated", ""))
                if (now - generated).days <= 30:
                    weekly_emotionals.append(report)
        except Exception:
            pass

    drift_episodes = _gather_drift_episodes(days=30)
    all_episodes = _gather_episodes(days=30)
    imprint_data = _gather_imprint_data()
    us_data = _read_us_md()

    from daemon.temperament import get_temperament_status
    temp_status = get_temperament_status()

    temp_trajectory = []
    for wd in weekly_emotionals:
        tg = wd.get("temperament_growth", {})
        temp_trajectory.append({
            "week": wd["id"],
            "adjustments": tg.get("adjustments", {}),
            "drift": tg.get("drift_from_factory", {}),
        })

    rel_trajectory = []
    for wd in weekly_emotionals:
        rel = wd.get("relationship", {})
        rel_trajectory.append({
            "week": wd["id"],
            "trajectory": rel.get("trajectory", "unknown"),
            "drift_ratio": rel.get("drift_ratio", 0),
        })

    trajectories = [r["trajectory"] for r in rel_trajectory]
    dominant_trajectory = "unknown"
    if trajectories:
        dominant_trajectory = Counter(trajectories).most_common(1)[0][0]

    total_episodes = len(all_episodes)

    def _monthly_emo_summary(drift_count, total_count, trajectory, temp_st, weekly_dreams, usd):
        parts = []
        if total_count > 0:
            ratio = round(drift_count / total_count * 100)
            parts.append(f"{drift_count}/{total_count} sessions were emotional ({ratio}%).")
        trajectory_labels = {
            "deepening": "Overall trend: deepening connection.",
            "plateau": "Overall trend: plateau — mostly work.",
            "straining": "Overall trend: some emotional strain.",
            "warm": "Overall trend: warm and present.",
            "stable": "Overall trend: stable.",
        }
        parts.append(trajectory_labels.get(trajectory, "Trajectory unclear."))
        drift = temp_st.get("drift", {})
        if drift:
            shifts = [f"{k} {v:+.3f}" for k, v in drift.items()]
            parts.append(f"Temperament drift from factory: {', '.join(shifts)}.")
        else:
            parts.append("Temperament at factory baseline.")
        parts.append(f"Based on {len(weekly_dreams)} weekly emotional dream(s).")
        if usd.get("total_entries", 0) > 0:
            parts.append(f"{usd['total_entries']} total moments saved in us.md.")
        return " ".join(parts)

    report = {
        "id": f"{month_id}-emotional", "type": "monthly_emotional",
        "generated": now.isoformat(),
        "period": {"start": (now - timedelta(days=30)).isoformat()[:10], "end": now.isoformat()[:10]},
        "weekly_dreams_analyzed": len(weekly_emotionals),
        "drift_sessions_total": len(drift_episodes),
        "total_sessions": total_episodes,
        "drift_ratio": round(len(drift_episodes) / total_episodes, 2) if total_episodes > 0 else 0,
        "dominant_trajectory": dominant_trajectory,
        "temperament_evolution": {
            "current": temp_status["current"], "factory": temp_status["factory"],
            "total_drift": temp_status["drift"], "weekly_trajectory": temp_trajectory,
        },
        "relationship_evolution": {
            "dominant": dominant_trajectory, "weekly_trajectory": rel_trajectory,
        },
        "imprint_summary": {
            "active": imprint_data["active_count"], "archived_total": imprint_data["archived_count"],
        },
        "us_md": us_data,
        "summary": _monthly_emo_summary(
            len(drift_episodes), total_episodes, dominant_trajectory,
            temp_status, weekly_emotionals, us_data
        ),
    }

    filepath = EMOTIONAL_DIR / f"{month_id}.json"
    filepath.write_text(json.dumps(report, indent=2))
    monthly_latest = EMOTIONAL_DIR / "monthly-latest.json"
    monthly_latest.write_text(json.dumps(report, indent=2))

    return report
