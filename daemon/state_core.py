"""
Elara State Core — shared constants, storage, and decay mechanics.

This is the foundation that mood, sessions, and temperament all depend on.
Everything here is internal — external code imports from daemon.state (the re-export layer).
"""

import json
import math
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from daemon.emotions import get_primary_emotion

STATE_FILE = Path.home() / ".claude" / "elara-state.json"
MOOD_JOURNAL_FILE = Path.home() / ".claude" / "elara-mood-journal.jsonl"
IMPRINT_ARCHIVE_FILE = Path.home() / ".claude" / "elara-imprint-archive.jsonl"
TEMPERAMENT_LOG_FILE = Path.home() / ".claude" / "elara-temperament-log.jsonl"

# My temperament - who I am at my core, where I return to
TEMPERAMENT = {
    "valence": 0.55,
    "energy": 0.5,
    "openness": 0.65,
}

# Factory defaults — the unchanging original
FACTORY_TEMPERAMENT = {
    "valence": 0.55,
    "energy": 0.5,
    "openness": 0.65,
}

TEMPERAMENT_MAX_DRIFT = 0.15

# Decay configuration
DECAY_RATE = 0.05
RESIDUE_DECAY_RATE = 0.02
NOISE_SCALE = 0.02

DEFAULT_STATE = {
    "mood": {
        "valence": 0.55,
        "energy": 0.5,
        "openness": 0.65,
    },
    "temperament": TEMPERAMENT.copy(),
    "imprints": [],
    "residue": [],
    "last_update": None,
    "last_session_end": None,
    "consolidation": {
        "last_idle_start": None,
        "last_idle_quality": None,
        "sleep_debt": 0,
    },
    "session_mood_start": None,
    "allostatic_load": 0,
    "flags": {
        "had_deep_conversation": False,
        "user_seemed_stressed": False,
        "user_seemed_happy": False,
        "late_night_session": False,
        "long_session": False,
    },
    "current_session": {
        "id": None,
        "type": None,
        "started": None,
        "projects": [],
        "auto_detected_type": None,
    }
}

SESSION_TYPE_RULES = {
    "drift_hours": [(22, 24), (0, 6)],
    "work_hours": [(9, 18)],
    "mixed_hours": [(6, 9), (18, 22)],
}


def _log_mood(state: dict, reason: Optional[str] = None, trigger: str = "adjust") -> None:
    """Append mood snapshot to journal."""
    try:
        v = round(state["mood"]["valence"], 3)
        e = round(state["mood"]["energy"], 3)
        o = round(state["mood"]["openness"], 3)
        emotion = get_primary_emotion(v, e, o)

        entry = {
            "ts": datetime.now().isoformat(),
            "v": v, "e": e, "o": o,
            "emotion": emotion,
            "reason": reason,
            "trigger": trigger,
            "episode": state.get("current_session", {}).get("id"),
        }
        MOOD_JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MOOD_JOURNAL_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _archive_imprint(imprint: dict) -> None:
    """Save dying imprint to archive."""
    try:
        entry = {"archived": datetime.now().isoformat(), **imprint}
        IMPRINT_ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(IMPRINT_ARCHIVE_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _load_state() -> dict:
    """Load current emotional state."""
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if "temperament" not in state:
                state["temperament"] = TEMPERAMENT.copy()
            if "imprints" not in state:
                state["imprints"] = []
            if "consolidation" not in state:
                state["consolidation"] = DEFAULT_STATE["consolidation"].copy()
            if "allostatic_load" not in state:
                state["allostatic_load"] = 0
            if "current_session" not in state:
                state["current_session"] = DEFAULT_STATE["current_session"].copy()
            return state
        except json.JSONDecodeError:
            pass
    return DEFAULT_STATE.copy()


def _save_state(data: dict) -> None:
    """Save emotional state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["last_update"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(data, indent=2))


def _apply_time_decay(state: dict) -> dict:
    """Apply time-based decay toward temperament."""
    if not state.get("last_update"):
        return state

    try:
        last_update = datetime.fromisoformat(state["last_update"])
        hours_passed = (datetime.now() - last_update).total_seconds() / 3600
    except (ValueError, TypeError):
        return state

    if hours_passed < 0.01:
        return state

    temperament = state.get("temperament", TEMPERAMENT)
    decay_factor = 1 - math.exp(-DECAY_RATE * hours_passed)

    for key in ["valence", "energy", "openness"]:
        current = state["mood"][key]
        baseline = temperament.get(key, 0.5)
        drift = (baseline - current) * decay_factor
        noise = random.gauss(0, NOISE_SCALE) if hours_passed > 0.1 else 0
        new_val = current + drift + noise

        if key == "valence":
            state["mood"][key] = max(-1, min(1, new_val))
        else:
            state["mood"][key] = max(0, min(1, new_val))

    state["imprints"] = _decay_imprints(state.get("imprints", []), hours_passed)
    return state


def _decay_imprints(imprints: List[dict], hours: float) -> List[dict]:
    """Decay emotional imprints, archive dead ones."""
    decay_factor = 1 - math.exp(-RESIDUE_DECAY_RATE * hours)

    surviving = []
    for imp in imprints:
        new_strength = imp.get("strength", 0.5) * (1 - decay_factor)
        if new_strength > 0.1:
            imp["strength"] = new_strength
            surviving.append(imp)
        else:
            _archive_imprint(imp)

    return surviving[-20:]
