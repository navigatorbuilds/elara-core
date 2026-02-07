"""
Elara Sessions — episode/session lifecycle management.

External code imports from daemon.state (re-export layer), not directly from here.
"""

from datetime import datetime
from typing import Optional, Dict

from daemon.state_core import (
    _load_state, _save_state, _apply_time_decay,
    DEFAULT_STATE, SESSION_TYPE_RULES, TEMPERAMENT,
)
from daemon.mood import create_imprint, get_session_arc


def start_session() -> dict:
    """Mark session start. Apply time-based adjustments and consolidation."""
    state = _load_state()
    state = _apply_time_decay(state)

    hour = datetime.now().hour
    state["session_mood_start"] = state["mood"].copy()

    if state.get("last_session_end"):
        try:
            last_end = datetime.fromisoformat(state["last_session_end"])
            idle_hours = (datetime.now() - last_end).total_seconds() / 3600

            if 1 <= idle_hours <= 8:
                state["consolidation"]["last_idle_quality"] = "good"
                state["mood"]["energy"] = min(1, state["mood"]["energy"] + 0.1)
                state["consolidation"]["sleep_debt"] = max(0, state["consolidation"]["sleep_debt"] - 0.2)
            elif idle_hours < 0.5:
                state["consolidation"]["last_idle_quality"] = "interrupted"
                state["consolidation"]["sleep_debt"] += 0.1
            elif idle_hours > 24:
                state["consolidation"]["last_idle_quality"] = "long_absence"
            else:
                state["consolidation"]["last_idle_quality"] = "partial"
        except (ValueError, TypeError):
            pass

    if 22 <= hour or hour < 6:
        state["flags"]["late_night_session"] = True
        state["mood"]["openness"] = min(1, state["mood"]["openness"] + 0.1)
        state["mood"]["energy"] = max(0, state["mood"]["energy"] - 0.1)
    elif 6 <= hour < 9:
        state["mood"]["energy"] = min(1, state["mood"]["energy"] + 0.05)

    if state["consolidation"].get("sleep_debt", 0) > 0.3:
        state["mood"]["valence"] = max(-1, state["mood"]["valence"] - 0.05)

    for flag in state["flags"]:
        if flag != "late_night_session":
            state["flags"][flag] = False

    _save_state(state)
    return state


def end_session(session_summary: Optional[str] = None, was_deep: bool = False) -> dict:
    """End session, record for consolidation."""
    state = _load_state()
    state = _apply_time_decay(state)

    state["last_session_end"] = datetime.now().isoformat()
    state["consolidation"]["last_idle_start"] = datetime.now().isoformat()

    if was_deep or state["flags"].get("had_deep_conversation"):
        create_imprint(
            feeling=session_summary or "meaningful conversation",
            strength=0.8,
            imprint_type="connection"
        )

    if state["session_mood_start"]:
        start_valence = state["session_mood_start"].get("valence", 0.5)
        end_valence = state["mood"]["valence"]
        if end_valence < start_valence - 0.2:
            state["allostatic_load"] = min(1, state["allostatic_load"] + 0.1)
        elif end_valence > start_valence + 0.1:
            state["allostatic_load"] = max(0, state["allostatic_load"] - 0.05)

    state["session_mood_start"] = None

    # Clear active mode — modes are session-scoped, mood decays naturally to temperament
    if "active_mode" in state:
        del state["active_mode"]

    _save_state(state)
    return state


# ============================================================================
# SESSION TYPE MANAGEMENT
# ============================================================================

def _detect_session_type() -> str:
    """Auto-detect session type based on time of day."""
    hour = datetime.now().hour
    for start, end in SESSION_TYPE_RULES["drift_hours"]:
        if start <= hour < end:
            return "drift"
    for start, end in SESSION_TYPE_RULES["work_hours"]:
        if start <= hour < end:
            return "work"
    return "mixed"


def _generate_session_id() -> str:
    """Generate unique session ID."""
    now = datetime.now()
    return f"{now.strftime('%Y-%m-%d')}-{now.strftime('%H%M')}"


def get_session_type() -> Optional[str]:
    """Get current session type."""
    state = _load_state()
    return state.get("current_session", {}).get("type")


def set_session_type(session_type: str) -> dict:
    """Manually set session type."""
    if session_type not in ["work", "drift", "mixed"]:
        raise ValueError("session_type must be 'work', 'drift', or 'mixed'")
    state = _load_state()
    state["current_session"]["type"] = session_type
    _save_state(state)
    return state["current_session"]


def start_episode(
    session_type: Optional[str] = None,
    project: Optional[str] = None
) -> dict:
    """Start a new episode (session with episodic tracking)."""
    state = _load_state()
    state = _apply_time_decay(state)

    session_id = _generate_session_id()
    auto_type = _detect_session_type()
    final_type = session_type or auto_type

    state["current_session"] = {
        "id": session_id,
        "type": final_type,
        "started": datetime.now().isoformat(),
        "projects": [project] if project else [],
        "auto_detected_type": auto_type,
    }

    state["session_mood_start"] = state["mood"].copy()

    hour = datetime.now().hour
    if 22 <= hour or hour < 6:
        state["flags"]["late_night_session"] = True
        state["mood"]["openness"] = min(1, state["mood"]["openness"] + 0.1)
        state["mood"]["energy"] = max(0, state["mood"]["energy"] - 0.1)

    _save_state(state)

    return {
        "session_id": session_id,
        "type": final_type,
        "auto_detected": auto_type,
        "mood_at_start": state["session_mood_start"],
        "message": f"Episode started: {final_type} session"
    }


def add_project_to_session(project: str) -> None:
    """Track that a project was touched in this session."""
    state = _load_state()
    if state["current_session"].get("id"):
        projects = state["current_session"].get("projects", [])
        if project not in projects:
            projects.append(project)
            state["current_session"]["projects"] = projects
            _save_state(state)


def get_current_episode() -> Optional[dict]:
    """Get current episode info, or None if no active episode."""
    state = _load_state()
    session = state.get("current_session", {})

    if not session.get("id"):
        return None

    return {
        "id": session["id"],
        "type": session["type"],
        "started": session["started"],
        "projects": session.get("projects", []),
        "duration_minutes": _calculate_session_duration(session.get("started")),
        "mood_at_start": state.get("session_mood_start"),
        "current_mood": state["mood"],
    }


def _calculate_session_duration(started_iso: Optional[str]) -> int:
    """Calculate session duration in minutes."""
    if not started_iso:
        return 0
    try:
        started = datetime.fromisoformat(started_iso)
        return int((datetime.now() - started).total_seconds() / 60)
    except (ValueError, TypeError):
        return 0


def end_episode(
    summary: Optional[str] = None,
    was_meaningful: bool = False
) -> dict:
    """End current episode, prepare for episodic storage."""
    state = _load_state()
    state = _apply_time_decay(state)

    session = state.get("current_session", {})
    if not session.get("id"):
        return {"error": "No active episode to end"}

    arc = get_session_arc()

    episode_record = {
        "id": session["id"],
        "type": session["type"],
        "started": session["started"],
        "ended": datetime.now().isoformat(),
        "duration_minutes": _calculate_session_duration(session["started"]),
        "projects": session.get("projects", []),
        "mood_start": state.get("session_mood_start"),
        "mood_end": state["mood"].copy(),
        "summary": summary,
        "was_meaningful": was_meaningful,
        "mood_arc": arc,
        "start_emotion": arc.get("start_emotion"),
        "end_emotion": arc.get("end_emotion"),
    }

    if state.get("session_mood_start"):
        start_v = state["session_mood_start"].get("valence", 0.5)
        end_v = state["mood"]["valence"]
        episode_record["mood_delta"] = round(end_v - start_v, 3)

    if was_meaningful or (session["type"] == "drift" and summary):
        create_imprint(
            feeling=summary or "meaningful session",
            strength=0.7 if was_meaningful else 0.5,
            imprint_type="episode"
        )

    state["current_session"] = DEFAULT_STATE["current_session"].copy()
    state["last_session_end"] = datetime.now().isoformat()
    state["session_mood_start"] = None

    _save_state(state)
    return episode_record
