"""
Elara Dream Mode — Emotional dreams (weekly + monthly).

Drift processing, temperament growth, tone calibration, relationship tracking.
Analysis helpers in dream_emotional_analysis.py.
"""

import logging
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from daemon.schemas import atomic_write_json

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status,
    _gather_episodes, _gather_mood_journal,
    EMOTIONAL_DIR,
)
from daemon.dream_emotional_analysis import (
    compute_temperament_adjustments,
    analyze_drift_sessions,
    analyze_imprint_evolution,
    assess_relationship_trajectory,
    generate_tone_hints,
    generate_emotional_summary,
    generate_monthly_emotional_summary,
)

logger = logging.getLogger("elara.dream_emotional")


# ============================================================================
# Data gathering helpers
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
    except OSError:
        return {"exists": True, "total_entries": 0, "error": "parse failed"}


# ============================================================================
# Weekly emotional dream
# ============================================================================

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

    growth_result = compute_temperament_adjustments(
        drift_episodes, mood_journal, imprint_data, us_data, intention
    )

    from daemon.temperament import apply_emotional_growth, decay_temperament_toward_factory
    from daemon.temperament import get_temperament_status
    decay_temperament_toward_factory(rate=0.15)

    applied = {}
    if growth_result["adjustments"]:
        applied = apply_emotional_growth(growth_result["adjustments"], source="emotional_dream")

    temp_status = get_temperament_status()

    drift_analysis = analyze_drift_sessions(drift_episodes)
    imprint_evolution = analyze_imprint_evolution(imprint_data)
    relationship = assess_relationship_trajectory(all_episodes, drift_episodes, us_data, mood_journal)
    tone_hints = generate_tone_hints(drift_analysis, imprint_evolution, relationship, growth_result, temp_status)

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
        "summary": generate_emotional_summary(
            drift_analysis, imprint_evolution, relationship,
            growth_result, tone_hints, len(drift_episodes), len(all_episodes)
        ),
    }

    filepath = EMOTIONAL_DIR / f"{dream_id}.json"
    atomic_write_json(filepath, report)
    latest = EMOTIONAL_DIR / "latest.json"
    atomic_write_json(latest, report)

    status = _load_status()
    status["last_emotional"] = now.isoformat()
    status["emotional_count"] = status.get("emotional_count", 0) + 1
    _save_status(status)

    return report


# ============================================================================
# Monthly emotional dream
# ============================================================================

def monthly_emotional_dream() -> dict:
    """Monthly emotional evolution — long-term identity tracking."""
    _ensure_dirs()

    now = datetime.now()
    month_id = now.strftime("%Y-%m")

    weekly_emotionals = []
    for f in sorted(EMOTIONAL_DIR.glob("[0-9]*-W*-emotional.json")):
        try:
            report = json.loads(f.read_text())
            if report.get("type") == "emotional":
                generated = datetime.fromisoformat(report.get("generated", ""))
                if (now - generated).days <= 30:
                    weekly_emotionals.append(report)
        except (json.JSONDecodeError, OSError, ValueError):
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
        "summary": generate_monthly_emotional_summary(
            len(drift_episodes), total_episodes, dominant_trajectory,
            temp_status, weekly_emotionals, us_data
        ),
    }

    filepath = EMOTIONAL_DIR / f"{month_id}.json"
    atomic_write_json(filepath, report)
    monthly_latest = EMOTIONAL_DIR / "monthly-latest.json"
    atomic_write_json(monthly_latest, report)

    return report
