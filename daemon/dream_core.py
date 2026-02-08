# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Dream Core — shared constants, data gathering, status, and utilities.

All dream types depend on this. External code imports from daemon.dream (re-export layer).
"""

import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from core.paths import get_paths
from daemon.schemas import DreamStatus, load_validated, save_validated

logger = logging.getLogger("elara.dream_core")

# Storage
_p = get_paths()
DREAMS_DIR = _p.dreams_dir
WEEKLY_DIR = _p.dreams_weekly
MONTHLY_DIR = _p.dreams_monthly
THREADS_DIR = _p.dreams_threads
EMOTIONAL_DIR = _p.dreams_emotional
DREAM_STATUS_FILE = _p.dream_status


def _ensure_dirs():
    """Create dream storage directories."""
    for d in [DREAMS_DIR, WEEKLY_DIR, MONTHLY_DIR, THREADS_DIR, EMOTIONAL_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _load_status() -> dict:
    """Load dream status (last run timestamps)."""
    logger.debug("Loading dream status from %s", DREAM_STATUS_FILE)
    model = load_validated(DREAM_STATUS_FILE, DreamStatus)
    return model.model_dump()


def _save_status(status: dict):
    """Save dream status."""
    _ensure_dirs()
    logger.debug("Saving dream status to %s", DREAM_STATUS_FILE)
    model = DreamStatus.model_validate(status)
    save_validated(DREAM_STATUS_FILE, model)


# ============================================================================
# DATA GATHERING
# ============================================================================

def _gather_episodes(days: int = 7) -> List[dict]:
    """Get episodes from the last N days."""
    from memory.episodic import get_episodic
    episodic = get_episodic()
    all_episodes = episodic.get_recent_episodes(n=50)

    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for ep in all_episodes:
        try:
            started = datetime.fromisoformat(ep.get("started", ""))
            if started >= cutoff:
                recent.append(ep)
        except (ValueError, TypeError):
            pass
    return recent


def _gather_goals() -> dict:
    """Get current goal state."""
    from daemon.goals import list_goals, stale_goals
    active = list_goals(status="active")
    stale = stale_goals(days=7)
    done = list_goals(status="done")
    return {
        "active": active,
        "stale": stale,
        "done_recently": [
            g for g in done
            if (datetime.now() - datetime.fromisoformat(g["last_touched"])).days < 14
        ],
    }


def _gather_corrections() -> List[dict]:
    """Get all corrections."""
    from daemon.corrections import list_corrections
    return list_corrections(n=50)


def _gather_mood_journal(days: int = 7) -> List[dict]:
    """Get mood journal entries from last N days."""
    from daemon.state import read_mood_journal
    entries = read_mood_journal(n=200)
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for e in entries:
        try:
            ts = datetime.fromisoformat(e.get("ts", ""))
            if ts >= cutoff:
                recent.append(e)
        except (ValueError, TypeError):
            pass
    return recent


def _gather_memories(days: int = 7) -> List[dict]:
    """Get recent semantic memories."""
    from memory.vector import recall
    try:
        results = recall("recent work and conversations", n_results=50)
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for r in results:
            try:
                date_str = r.get("date", "")
                if date_str:
                    date = datetime.fromisoformat(date_str)
                    if date >= cutoff:
                        recent.append(r)
            except (ValueError, TypeError):
                recent.append(r)
        return recent
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Memory recall failed during dream: %s", e)
        return []


def _is_late(ts: str) -> bool:
    """Check if timestamp is late night (22:00-06:00)."""
    try:
        hour = datetime.fromisoformat(ts).hour
        return hour >= 22 or hour < 6
    except (ValueError, TypeError):
        return False


# ============================================================================
# DREAM STATUS & BOOT CHECK
# ============================================================================

def dream_status() -> dict:
    """Check when dreams last ran and if any are overdue."""
    status = _load_status()
    now = datetime.now()

    weekly_overdue = False
    monthly_overdue = False
    weekly_age_days = None
    monthly_age_days = None

    if status.get("last_weekly"):
        try:
            last_w = datetime.fromisoformat(status["last_weekly"])
            weekly_age_days = (now - last_w).days
            weekly_overdue = weekly_age_days >= 7
        except (ValueError, TypeError):
            weekly_overdue = True
    else:
        weekly_overdue = True

    if status.get("last_monthly"):
        try:
            last_m = datetime.fromisoformat(status["last_monthly"])
            monthly_age_days = (now - last_m).days
            monthly_overdue = monthly_age_days >= 30
        except (ValueError, TypeError):
            monthly_overdue = True
    else:
        monthly_overdue = True

    emotional_age_days = None
    if status.get("last_emotional"):
        try:
            last_e = datetime.fromisoformat(status["last_emotional"])
            emotional_age_days = (now - last_e).days
        except (ValueError, TypeError):
            pass

    return {
        "last_weekly": status.get("last_weekly"),
        "last_monthly": status.get("last_monthly"),
        "last_threads": status.get("last_threads"),
        "last_emotional": status.get("last_emotional"),
        "weekly_age_days": weekly_age_days,
        "monthly_age_days": monthly_age_days,
        "emotional_age_days": emotional_age_days,
        "weekly_overdue": weekly_overdue,
        "monthly_overdue": monthly_overdue,
        "weekly_count": status.get("weekly_count", 0),
        "monthly_count": status.get("monthly_count", 0),
        "emotional_count": status.get("emotional_count", 0),
    }


def dream_boot_check() -> Optional[str]:
    """Check if any dreams are overdue. Called by awareness_boot."""
    ds = dream_status()
    notices = []

    if ds["weekly_overdue"]:
        if ds["weekly_age_days"] is not None:
            notices.append(f"Weekly dream overdue ({ds['weekly_age_days']}d since last)")
        else:
            notices.append("Weekly dream never run")

    if ds["monthly_overdue"]:
        if ds["monthly_age_days"] is not None:
            notices.append(f"Monthly dream overdue ({ds['monthly_age_days']}d since last)")
        else:
            notices.append("Monthly dream never run")

    if not notices:
        return None
    return " | ".join(notices)


def read_latest_dream(dream_type: str = "weekly") -> Optional[dict]:
    """Read the latest dream report."""
    logger.debug("Reading latest %s dream report", dream_type)
    if dream_type == "weekly":
        latest = WEEKLY_DIR / "latest.json"
    elif dream_type == "monthly":
        latest = MONTHLY_DIR / "latest.json"
    elif dream_type == "threads":
        latest = THREADS_DIR / "latest.json"
    elif dream_type == "emotional":
        latest = EMOTIONAL_DIR / "latest.json"
    elif dream_type == "monthly_emotional":
        latest = EMOTIONAL_DIR / "monthly-latest.json"
    else:
        return None

    if latest.exists():
        try:
            return json.loads(latest.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None
