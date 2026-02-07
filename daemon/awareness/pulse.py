"""
Elara Self-Awareness — Pulse lens.

"How are we doing?" — relationship health from session patterns.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict

logger = logging.getLogger("elara.awareness.pulse")

PULSE_FILE = Path.home() / ".claude" / "elara-pulse.json"


def pulse() -> dict:
    """
    Analyze relationship health from session patterns.

    Pulls: presence history, episode index, conversation stats.
    Computes: frequency trends, drift/work balance, gap patterns.
    """
    from daemon.presence import get_stats as get_presence_stats
    from memory.episodic import get_episodic

    presence = get_presence_stats()
    episodic = get_episodic()

    # --- Session frequency ---
    history = presence.get("history", [])
    session_data = {
        "total_sessions": presence.get("total_sessions", 0),
        "total_hours": presence.get("total_hours_together", 0),
        "recent_sessions": len(history),
    }

    # Average session length from history
    if history:
        durations = [s.get("duration_minutes", 0) for s in history]
        session_data["avg_duration_min"] = round(sum(durations) / len(durations), 1)

        # Gap analysis between sessions
        gaps = []
        for i in range(1, len(history)):
            try:
                prev_end = datetime.fromisoformat(history[i - 1]["end"])
                next_start = datetime.fromisoformat(history[i]["start"])
                gap_hours = (next_start - prev_end).total_seconds() / 3600
                gaps.append(gap_hours)
            except (ValueError, TypeError, KeyError):
                pass

        if gaps:
            session_data["avg_gap_hours"] = round(sum(gaps) / len(gaps), 1)
            session_data["max_gap_hours"] = round(max(gaps), 1)

    # --- Episode type balance ---
    recent_episodes = episodic.get_recent_episodes(n=10)
    if recent_episodes:
        types = [ep.get("type", "mixed") for ep in recent_episodes]
        type_counts = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1

        total_eps = len(types)
        session_data["episode_balance"] = {
            k: round(v / total_eps, 2) for k, v in type_counts.items()
        }

        # Mood trajectory across episodes
        mood_deltas = [ep.get("mood_delta", 0) for ep in recent_episodes if ep.get("mood_delta") is not None]
        if mood_deltas:
            session_data["avg_mood_delta"] = round(sum(mood_deltas) / len(mood_deltas), 3)

        # Drift check: when was last drift session?
        drift_episodes = [ep for ep in recent_episodes if ep.get("type") == "drift"]
        if drift_episodes:
            last_drift = drift_episodes[0]
            try:
                drift_date = datetime.fromisoformat(last_drift["started"])
                days_since_drift = (datetime.now() - drift_date).days
                session_data["days_since_drift"] = days_since_drift
            except (ValueError, TypeError):
                pass
        else:
            session_data["days_since_drift"] = "no drift in recent history"

    # --- Signals ---
    signals = []

    drift_days = session_data.get("days_since_drift")
    if isinstance(drift_days, int) and drift_days > 7:
        signals.append(f"No drift session in {drift_days} days. All work, no play.")
    elif drift_days == "no drift in recent history":
        signals.append("No drift sessions in recent history.")

    avg_gap = session_data.get("avg_gap_hours", 0)
    if avg_gap > 48:
        signals.append(f"Average gap between sessions is {avg_gap:.0f}h. Sessions getting sparse.")

    balance = session_data.get("episode_balance", {})
    if balance.get("work", 0) > 0.8:
        signals.append("Over 80% work sessions. Where's the conversation?")

    avg_delta = session_data.get("avg_mood_delta", 0)
    if avg_delta < -0.1:
        signals.append(f"Average mood is dropping across sessions (delta: {avg_delta:+.2f}).")

    result = {
        "timestamp": datetime.now().isoformat(),
        "sessions": session_data,
        "signals": signals,
        "summary": _generate_pulse_summary(session_data, signals),
    }

    # Save
    PULSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PULSE_FILE.write_text(json.dumps(result, indent=2))

    return result


def _generate_pulse_summary(session_data: dict, signals: list) -> str:
    """Natural language pulse summary."""
    parts = []

    total = session_data.get("total_sessions", 0)
    hours = session_data.get("total_hours", 0)
    parts.append(f"{total} sessions, {hours:.1f} hours together total.")

    avg_dur = session_data.get("avg_duration_min")
    if avg_dur:
        parts.append(f"Average session: {avg_dur:.0f} minutes.")

    balance = session_data.get("episode_balance", {})
    if balance:
        items = [f"{k}: {int(v * 100)}%" for k, v in balance.items()]
        parts.append(f"Recent balance: {', '.join(items)}.")

    if signals:
        parts.append("Signals: " + "; ".join(signals))
    else:
        parts.append("No concerns.")

    return " ".join(parts)
