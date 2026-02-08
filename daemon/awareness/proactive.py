"""
Elara Self-Awareness — Proactive Presence.

"What should I notice?" — pattern detection surfaced at boot / mid-session.
Pure Python logic — zero token cost.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from core.paths import get_paths
from daemon.events import bus, Events

logger = logging.getLogger("elara.awareness.proactive")

PROACTIVE_SESSION_FILE = get_paths().proactive_session


def _load_proactive_session() -> dict:
    """Load proactive session state."""
    if PROACTIVE_SESSION_FILE.exists():
        try:
            return json.loads(PROACTIVE_SESSION_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "observations_surfaced": 0,
        "last_observation_time": None,
        "surfaced_types": [],
        "session_start": None,
        "cooldown_until": None,
    }


def _save_proactive_session(data: dict) -> None:
    """Save proactive session state."""
    PROACTIVE_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROACTIVE_SESSION_FILE.write_text(json.dumps(data, indent=2))


def _record_observation(obs_type: str) -> None:
    """Record that an observation was surfaced (for cooldown tracking)."""
    session = _load_proactive_session()
    session["observations_surfaced"] += 1
    session["last_observation_time"] = datetime.now().isoformat()
    session["surfaced_types"].append(obs_type)
    session["surfaced_types"] = session["surfaced_types"][-10:]
    _save_proactive_session(session)


def _can_observe() -> bool:
    """Check if we're allowed to surface another observation."""
    session = _load_proactive_session()

    # Max 3 observations per session
    if session["observations_surfaced"] >= 3:
        return False

    # Minimum 5 minutes between observations
    if session.get("last_observation_time"):
        try:
            last = datetime.fromisoformat(session["last_observation_time"])
            if (datetime.now() - last).total_seconds() < 300:
                return False
        except (ValueError, TypeError):
            pass

    return True


def reset_proactive_session() -> None:
    """Reset proactive session state (call at session start)."""
    data = {
        "observations_surfaced": 0,
        "last_observation_time": None,
        "surfaced_types": [],
        "session_start": datetime.now().isoformat(),
        "cooldown_until": None,
    }
    _save_proactive_session(data)


# --- Observation generators — each returns an observation dict or None ---

def _check_session_gap() -> Optional[Dict]:
    """Detect notable gaps between sessions."""
    try:
        from daemon.presence import get_stats
        stats = get_stats()
    except ImportError:
        return None

    absence_min = stats.get("absence_minutes")
    if absence_min is None:
        return None

    absence_hours = absence_min / 60

    if absence_hours > 48:
        days = int(absence_hours / 24)
        return {
            "type": "long_gap",
            "severity": "notable",
            "message": f"It's been {days} days. That's unusual for us.",
            "suggestion": "check_in",
        }

    return None


def _check_time_pattern() -> Optional[Dict]:
    """Detect unusual session timing."""
    hour = datetime.now().hour

    if 2 <= hour < 5:
        return {
            "type": "very_late",
            "severity": "gentle",
            "message": "It's past 2 AM. You should probably sleep.",
            "suggestion": "acknowledge_late",
        }

    return None


def _check_mood_trend() -> Optional[Dict]:
    """Detect mood trends across recent journal entries."""
    try:
        from daemon.state import read_mood_journal
        from daemon.emotions import get_primary_emotion
    except ImportError:
        return None

    journal = read_mood_journal(n=20)
    if len(journal) < 5:
        return None

    recent = journal[-10:]
    valences = [e.get("v", 0.5) for e in recent]
    energies = [e.get("e", 0.5) for e in recent]

    v_trend = _simple_trend(valences)

    avg_energy = sum(energies) / len(energies)
    if avg_energy < 0.3:
        current_emotion = get_primary_emotion(valences[-1], energies[-1], recent[-1].get("o", 0.5))
        return {
            "type": "low_energy",
            "severity": "gentle",
            "message": f"Energy's been low lately. Currently feeling {current_emotion}.",
            "suggestion": "lighter_work",
            "data": {"avg_energy": round(avg_energy, 2)},
        }

    if v_trend < -0.03:
        return {
            "type": "valence_declining",
            "severity": "notable",
            "message": "Mood's been drifting down across recent interactions.",
            "suggestion": "check_in",
            "data": {"trend": round(v_trend, 3)},
        }

    if v_trend > 0.04:
        return {
            "type": "valence_rising",
            "severity": "positive",
            "message": "Mood's been trending up. Good stretch.",
            "suggestion": "acknowledge",
            "data": {"trend": round(v_trend, 3)},
        }

    return None


def _check_session_pattern() -> Optional[Dict]:
    """Detect patterns in session history (all late nights, no drift, etc.)."""
    try:
        from memory.episodic import get_episodic
    except ImportError:
        return None

    episodic = get_episodic()
    recent = episodic.get_recent_episodes(n=10)

    if len(recent) < 3:
        return None

    types = [ep.get("type", "work") for ep in recent]
    work_count = types.count("work")
    drift_count = types.count("drift")

    if work_count >= 5 and drift_count == 0:
        return {
            "type": "all_work_no_drift",
            "severity": "gentle",
            "message": f"Last {len(recent)} sessions have been all work. No drift time.",
            "suggestion": "balance",
        }

    late_count = 0
    for ep in recent[:5]:
        started = ep.get("started", "")
        try:
            hour = datetime.fromisoformat(started).hour
            if hour >= 22 or hour < 6:
                late_count += 1
        except (ValueError, TypeError):
            pass

    if late_count >= 4:
        return {
            "type": "all_late_night",
            "severity": "gentle",
            "message": "You've been burning the midnight oil. A lot.",
            "suggestion": "sleep_pattern",
        }

    return None


def _check_milestone_streak() -> Optional[Dict]:
    """Detect milestone streaks — many things shipped recently."""
    try:
        from memory.episodic import get_episodic
    except ImportError:
        return None

    episodic = get_episodic()
    recent = episodic.get_recent_episodes(n=5)

    total_milestones = 0
    completions = 0
    for ep in recent:
        milestones = ep.get("milestones", [])
        total_milestones += len(milestones)
        completions += sum(1 for m in milestones if m.get("type") == "completion")

    if completions >= 3:
        return {
            "type": "shipping_streak",
            "severity": "positive",
            "message": f"We've shipped {completions} things in the last {len(recent)} sessions. Productive stretch.",
            "suggestion": "acknowledge",
        }

    return None


def _check_stale_goals() -> Optional[Dict]:
    """Check if goals are going stale."""
    try:
        from daemon.goals import stale_goals
    except ImportError:
        return None

    stale = stale_goals(days=7)
    if stale and len(stale) >= 2:
        names = [g["title"][:40] for g in stale[:3]]
        return {
            "type": "stale_goals",
            "severity": "notable",
            "message": f"{len(stale)} goals haven't been touched in a week: {', '.join(names)}",
            "suggestion": "review_goals",
        }

    return None


def _check_imprint_weight() -> Optional[Dict]:
    """Check if carrying heavy emotional imprints."""
    try:
        from daemon.state import get_imprints
    except ImportError:
        return None

    imprints = get_imprints(min_strength=0.6)
    if len(imprints) >= 3:
        feelings = [imp.get("feeling", "something")[:30] for imp in imprints[:3]]
        return {
            "type": "heavy_imprints",
            "severity": "gentle",
            "message": f"Carrying a lot emotionally right now: {'; '.join(feelings)}",
            "suggestion": "acknowledge",
        }

    return None


# --- Proactive API ---

def get_boot_observations() -> List[Dict]:
    """
    Run all checks at session start. Returns observations worth surfacing.
    Resets session counter.
    """
    reset_proactive_session()

    observations = []
    checkers = [
        _check_session_gap,
        _check_time_pattern,
        _check_mood_trend,
        _check_session_pattern,
        _check_stale_goals,
        _check_imprint_weight,
    ]

    for checker in checkers:
        try:
            obs = checker()
            if obs:
                observations.append(obs)
        except Exception as e:
            logger.warning("Boot observation checker %s failed: %s", checker.__name__, e)

    return observations


def get_mid_session_observations() -> List[Dict]:
    """
    Check for observations during a session. Respects cooldown.
    Call this periodically or at natural breaks.
    """
    if not _can_observe():
        return []

    observations = []
    session = _load_proactive_session()
    already_surfaced = set(session.get("surfaced_types", []))

    checkers = [
        _check_mood_trend,
        _check_milestone_streak,
        _check_imprint_weight,
    ]

    for checker in checkers:
        try:
            obs = checker()
            if obs and obs["type"] not in already_surfaced:
                observations.append(obs)
        except Exception as e:
            logger.warning("Mid-session observation checker %s failed: %s", checker.__name__, e)

    return observations


def surface_observation(observation: Dict) -> str:
    """
    Mark an observation as surfaced and return the message.
    This is what I actually say to the user.
    """
    _record_observation(observation["type"])
    bus.emit(Events.OBSERVATION_SURFACED, {"type": observation["type"], "severity": observation.get("severity", "")}, source="proactive")
    return observation["message"]


def get_observation_count() -> int:
    """How many observations have been surfaced this session?"""
    session = _load_proactive_session()
    return session.get("observations_surfaced", 0)


# --- Helpers ---

def _simple_trend(values: list) -> float:
    """
    Calculate simple linear trend.
    Returns slope: positive = rising, negative = falling.
    """
    n = len(values)
    if n < 2:
        return 0

    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0

    return numerator / denominator
