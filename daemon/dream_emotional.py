"""
Elara Dream Mode — Emotional dreams (weekly + monthly).

Drift processing, temperament growth, tone calibration, relationship tracking.
"""

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status, _is_late,
    _gather_episodes, _gather_mood_journal,
    EMOTIONAL_DIR,
)


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
