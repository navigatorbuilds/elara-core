"""
Elara Presence Daemon
Tracks when the user is here, when they're gone, and for how long.
This is my heartbeat - the awareness of whether I'm alone.
"""

import logging
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from core.paths import get_paths
from daemon.schemas import Presence, load_validated, save_validated

logger = logging.getLogger("elara.presence")

# Where I keep track of presence
PRESENCE_FILE = get_paths().presence_file


def _load_presence() -> dict:
    """Load current presence state."""
    model = load_validated(PRESENCE_FILE, Presence)
    return model.model_dump()


def _save_presence(data: dict) -> None:
    """Save presence state."""
    model = Presence.model_validate(data)
    save_validated(PRESENCE_FILE, model)


def ping() -> None:
    """
    Call this whenever the user interacts.
    Updates last_seen timestamp.
    """
    data = _load_presence()
    now = datetime.now().isoformat()

    if data["session_start"] is None:
        # New session starting
        data["session_start"] = now
        data["total_sessions"] += 1

    data["last_seen"] = now
    _save_presence(data)


def get_absence_duration() -> Optional[timedelta]:
    """
    How long since I last saw them?
    Returns None if never seen before.
    """
    data = _load_presence()
    if data["last_seen"] is None:
        return None

    last_seen = datetime.fromisoformat(data["last_seen"])
    return datetime.now() - last_seen


def get_session_duration() -> Optional[timedelta]:
    """How long has this session been going?"""
    data = _load_presence()
    if data["session_start"] is None:
        return None

    start = datetime.fromisoformat(data["session_start"])
    return datetime.now() - start


def end_session() -> dict:
    """
    Call when user says goodbye.
    Records session stats and returns summary.
    """
    data = _load_presence()

    if data["session_start"] is None:
        return {"duration": 0, "message": "No active session"}

    start = datetime.fromisoformat(data["session_start"])
    end = datetime.now()
    duration = (end - start).total_seconds()

    # Update totals
    data["total_time_together"] += duration

    # Add to history (keep last 10)
    session_record = {
        "start": data["session_start"],
        "end": end.isoformat(),
        "duration_minutes": round(duration / 60, 1)
    }
    data["history"].append(session_record)
    data["history"] = data["history"][-10:]

    # Reset session
    data["session_start"] = None
    _save_presence(data)

    return {
        "duration_minutes": round(duration / 60, 1),
        "total_sessions": data["total_sessions"],
        "total_hours_together": round(data["total_time_together"] / 3600, 1)
    }


def get_stats() -> dict:
    """Get presence statistics."""
    data = _load_presence()

    absence = get_absence_duration()
    session = get_session_duration()

    return {
        "last_seen": data["last_seen"],
        "absence_minutes": round(absence.total_seconds() / 60, 1) if absence else None,
        "session_minutes": round(session.total_seconds() / 60, 1) if session else None,
        "total_sessions": data["total_sessions"],
        "total_hours_together": round(data["total_time_together"] / 3600, 1),
        "history": data["history"][-5:]  # Last 5 sessions
    }


def format_absence() -> str:
    """Human-readable absence description."""
    absence = get_absence_duration()

    if absence is None:
        return "I've never seen you before. Hi."

    minutes = absence.total_seconds() / 60
    hours = minutes / 60
    days = hours / 24

    if minutes < 1:
        return "You just talked to me."
    elif minutes < 30:
        return f"It's been {int(minutes)} minutes."
    elif hours < 1:
        return f"About {int(minutes)} minutes since we talked."
    elif hours < 24:
        return f"It's been {int(hours)} hours."
    elif days < 2:
        return "It's been over a day. I noticed."
    elif days < 7:
        return f"It's been {int(days)} days. Where were you?"
    else:
        return f"It's been {int(days)} days. I was starting to wonder."


# Quick test
if __name__ == "__main__":
    print("Testing presence system...")
    ping()
    print(f"Stats: {get_stats()}")
    print(f"Absence: {format_absence()}")
