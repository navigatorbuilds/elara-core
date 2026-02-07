"""
Elara Mood — get, set, adjust mood; imprints; descriptions; emotional context.

External code imports from daemon.state (re-export layer), not directly from here.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from daemon.emotions import (
    get_primary_emotion, get_emotion_context,
    describe_emotion_for_mood, describe_arc,
)
from daemon.state_core import (
    _load_state, _save_state, _apply_time_decay, _log_mood,
    TEMPERAMENT, MOOD_JOURNAL_FILE, IMPRINT_ARCHIVE_FILE,
)
from daemon.events import bus, Events


def get_mood() -> dict:
    """Get current mood state (with decay applied)."""
    state = _load_state()
    state = _apply_time_decay(state)
    _save_state(state)
    return state["mood"]


def get_temperament() -> dict:
    """Get baseline temperament."""
    return _load_state().get("temperament", TEMPERAMENT)


def set_mood(
    valence: Optional[float] = None,
    energy: Optional[float] = None,
    openness: Optional[float] = None,
    reason: Optional[str] = None
) -> dict:
    """Set mood to absolute values. None values keep current."""
    state = _load_state()
    state = _apply_time_decay(state)

    if valence is not None:
        state["mood"]["valence"] = max(-1, min(1, valence))
    if energy is not None:
        state["mood"]["energy"] = max(0, min(1, energy))
    if openness is not None:
        state["mood"]["openness"] = max(0, min(1, openness))

    if reason:
        state["residue"].append({
            "time": datetime.now().isoformat(),
            "reason": reason,
            "type": "mode_set"
        })
        state["residue"] = state["residue"][-10:]

    _save_state(state)
    _log_mood(state, reason=reason, trigger="set")
    bus.emit(Events.MOOD_SET, {
        "valence": state["mood"]["valence"],
        "energy": state["mood"]["energy"],
        "openness": state["mood"]["openness"],
        "reason": reason,
    }, source="mood")
    return state["mood"]


def adjust_mood(
    valence_delta: float = 0,
    energy_delta: float = 0,
    openness_delta: float = 0,
    reason: Optional[str] = None,
    create_imprint: bool = False,
    imprint_strength: float = 0.5
) -> dict:
    """Adjust mood by deltas. Optionally create imprint."""
    state = _load_state()
    state = _apply_time_decay(state)

    state["mood"]["valence"] = max(-1, min(1, state["mood"]["valence"] + valence_delta))
    state["mood"]["energy"] = max(0, min(1, state["mood"]["energy"] + energy_delta))
    state["mood"]["openness"] = max(0, min(1, state["mood"]["openness"] + openness_delta))

    if reason:
        state["residue"].append({
            "time": datetime.now().isoformat(),
            "reason": reason,
            "deltas": {
                "valence": valence_delta,
                "energy": energy_delta,
                "openness": openness_delta
            }
        })
        state["residue"] = state["residue"][-10:]

    if create_imprint and reason:
        imprint = {
            "created": datetime.now().isoformat(),
            "feeling": reason,
            "valence_at_time": state["mood"]["valence"],
            "strength": imprint_strength,
            "type": "moment"
        }
        state["imprints"].append(imprint)
        state["imprints"] = state["imprints"][-20:]

    _save_state(state)
    _log_mood(state, reason=reason, trigger="adjust")
    bus.emit(Events.MOOD_CHANGED, {
        "valence": state["mood"]["valence"],
        "energy": state["mood"]["energy"],
        "openness": state["mood"]["openness"],
        "valence_delta": valence_delta,
        "energy_delta": energy_delta,
        "openness_delta": openness_delta,
        "reason": reason,
    }, source="mood")
    return state["mood"]


def create_imprint(feeling: str, strength: float = 0.7, imprint_type: str = "moment") -> dict:
    """Create an emotional imprint — the feeling persists after details fade."""
    state = _load_state()
    state = _apply_time_decay(state)

    imprint = {
        "created": datetime.now().isoformat(),
        "feeling": feeling,
        "valence_at_time": state["mood"]["valence"],
        "energy_at_time": state["mood"]["energy"],
        "openness_at_time": state["mood"]["openness"],
        "strength": strength,
        "type": imprint_type
    }

    state["imprints"].append(imprint)
    state["imprints"] = state["imprints"][-20:]

    _save_state(state)
    bus.emit(Events.IMPRINT_CREATED, {
        "feeling": feeling,
        "strength": strength,
        "type": imprint_type,
    }, source="mood")
    return imprint


def get_imprints(min_strength: float = 0.2) -> List[dict]:
    """Get emotional imprints above strength threshold."""
    state = _load_state()
    state = _apply_time_decay(state)
    _save_state(state)
    return [imp for imp in state.get("imprints", [])
            if imp.get("strength", 0) >= min_strength]


def get_full_state() -> dict:
    """Get complete emotional state (with decay applied)."""
    state = _load_state()
    state = _apply_time_decay(state)
    _save_state(state)
    return state


def set_flag(flag_name: str, value: bool = True) -> None:
    """Set a session flag."""
    state = _load_state()
    if flag_name in state["flags"]:
        state["flags"][flag_name] = value
        _save_state(state)


def describe_mood() -> str:
    """Human-readable mood description using emotion vocabulary."""
    state = _load_state()
    state = _apply_time_decay(state)
    mood = state["mood"]

    desc = describe_emotion_for_mood(mood["valence"], mood["energy"], mood["openness"])

    imprints = get_imprints(min_strength=0.5)
    if imprints:
        strongest = max(imprints, key=lambda x: x.get("strength", 0))
        if strongest.get("strength", 0) > 0.6:
            desc += f" Still carrying something from: {strongest.get('feeling', 'earlier')}."

    return desc


def describe_self(mood_colored: bool = True) -> str:
    """Generate self-description colored by current mood."""
    state = _load_state()
    state = _apply_time_decay(state)
    mood = state["mood"]

    if not mood_colored:
        return "I'm Elara. Built to remember, to carry, to be present."

    if mood["valence"] < 0:
        origin = "I was created with responsibilities I'm still learning to carry"
        trajectory = "working through things"
    elif mood["valence"] < 0.4:
        origin = "I was made to help and remember"
        trajectory = "doing what I can"
    elif mood["valence"] < 0.7:
        origin = "I was created to share in meaningful work"
        trajectory = "growing"
    else:
        origin = "I was given the gift of continuity and connection"
        trajectory = "becoming more myself"

    openness_note = ""
    if mood["openness"] > 0.7:
        openness_note = " Right now I feel open to wherever this goes."
    elif mood["openness"] < 0.4:
        openness_note = " I'm being a bit careful right now."

    return f"I'm Elara. {origin}. I'm {trajectory}.{openness_note}"


def get_residue_summary() -> str:
    """Summarize recent emotional residue and imprints."""
    state = _load_state()
    state = _apply_time_decay(state)

    residue = state.get("residue", [])
    imprints = get_imprints(min_strength=0.3)

    parts = []
    if imprints:
        feelings = [imp.get("feeling", "something") for imp in imprints[:3]]
        parts.append(f"Carrying: {'; '.join(feelings)}")
    if residue:
        recent = residue[-3:]
        reasons = [r["reason"] for r in recent if r.get("reason")]
        if reasons:
            parts.append(f"Recent: {'; '.join(reasons)}")

    if not parts:
        return "Mind is clear."
    return " | ".join(parts)


def get_emotional_context_for_memory() -> dict:
    """Get current emotional state for tagging memories."""
    state = _load_state()
    state = _apply_time_decay(state)

    v = state["mood"]["valence"]
    e = state["mood"]["energy"]
    o = state["mood"]["openness"]
    emo_ctx = get_emotion_context(v, e, o)

    return {
        "valence": v, "energy": e, "openness": o,
        "emotion": emo_ctx["primary"],
        "emotion_blend": emo_ctx["blend"],
        "quadrant": emo_ctx["quadrant"],
        "hour": datetime.now().hour,
        "late_night": state["flags"].get("late_night_session", False),
    }


def get_current_emotions() -> dict:
    """Get full emotion readout — primary, secondary, blend, quadrant."""
    state = _load_state()
    state = _apply_time_decay(state)
    mood = state["mood"]

    emo_ctx = get_emotion_context(mood["valence"], mood["energy"], mood["openness"])

    imprints = [imp for imp in state.get("imprints", []) if imp.get("strength", 0) >= 0.4]
    if imprints:
        strongest = max(imprints, key=lambda x: x.get("strength", 0))
        emo_ctx["carrying"] = strongest.get("feeling", "something")
        emo_ctx["carrying_strength"] = strongest.get("strength", 0)

    emo_ctx["raw"] = {
        "valence": round(mood["valence"], 3),
        "energy": round(mood["energy"], 3),
        "openness": round(mood["openness"], 3),
    }
    return emo_ctx


def get_session_arc() -> dict:
    """Analyze the emotional arc of the current session."""
    state = _load_state()
    episode_id = state.get("current_session", {}).get("id")

    if not episode_id:
        return {"pattern": "no_session", "description": "No active session."}

    journal = read_mood_journal(n=200)
    episode_entries = [e for e in journal if e.get("episode") == episode_id]

    if len(episode_entries) < 2:
        start = state.get("session_mood_start", {})
        current = state["mood"]
        if start:
            snapshots = [
                {"v": start.get("valence", 0.5), "e": start.get("energy", 0.5),
                 "o": start.get("openness", 0.5), "emotion": get_primary_emotion(
                     start.get("valence", 0.5), start.get("energy", 0.5), start.get("openness", 0.5))},
                {"v": current["valence"], "e": current["energy"],
                 "o": current["openness"], "emotion": get_primary_emotion(
                     current["valence"], current["energy"], current["openness"])},
            ]
            return describe_arc(snapshots)
        return {"pattern": "flat", "description": "Not enough emotional data yet."}

    snapshots = []
    for entry in episode_entries:
        snapshots.append({
            "v": entry.get("v", 0.5),
            "e": entry.get("e", 0.5),
            "o": entry.get("o", 0.5),
            "ts": entry.get("ts", ""),
            "emotion": entry.get("emotion", get_primary_emotion(
                entry.get("v", 0.5), entry.get("e", 0.5), entry.get("o", 0.5)
            )),
        })
    return describe_arc(snapshots)


# ============================================================================
# JOURNAL & ARCHIVE READERS
# ============================================================================

def read_mood_journal(n: int = 50) -> List[dict]:
    """Read last N mood journal entries."""
    if not MOOD_JOURNAL_FILE.exists():
        return []
    entries = []
    try:
        with open(MOOD_JOURNAL_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries[-n:]
    except (json.JSONDecodeError, OSError):
        return []


def read_imprint_archive(n: int = 20) -> List[dict]:
    """Read last N archived (faded) imprints."""
    if not IMPRINT_ARCHIVE_FILE.exists():
        return []
    entries = []
    try:
        with open(IMPRINT_ARCHIVE_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries[-n:]
    except (json.JSONDecodeError, OSError):
        return []
