"""
Elara Dream Core — shared constants, data gathering, status, and utilities.

All dream types depend on this. External code imports from daemon.dream (re-export layer).
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# Storage
DREAMS_DIR = Path.home() / ".claude" / "elara-dreams"
WEEKLY_DIR = DREAMS_DIR / "weekly"
MONTHLY_DIR = DREAMS_DIR / "monthly"
THREADS_DIR = DREAMS_DIR / "threads"
EMOTIONAL_DIR = DREAMS_DIR / "emotional"
DREAM_STATUS_FILE = DREAMS_DIR / "status.json"


def _ensure_dirs():
    """Create dream storage directories."""
    for d in [DREAMS_DIR, WEEKLY_DIR, MONTHLY_DIR, THREADS_DIR, EMOTIONAL_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _load_status() -> dict:
    """Load dream status (last run timestamps)."""
    if DREAM_STATUS_FILE.exists():
        try:
            return json.loads(DREAM_STATUS_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "last_weekly": None,
        "last_monthly": None,
        "last_threads": None,
        "weekly_count": 0,
        "monthly_count": 0,
    }


def _save_status(status: dict):
    """Save dream status."""
    _ensure_dirs()
    DREAM_STATUS_FILE.write_text(json.dumps(status, indent=2))


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
    except Exception:
        return []


def _is_late(ts: str) -> bool:
    """Check if timestamp is late night (22:00-06:00)."""
    try:
        hour = datetime.fromisoformat(ts).hour
        return hour >= 22 or hour < 6
    except Exception:
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
        except (json.JSONDecodeError, Exception):
            pass
    return None
