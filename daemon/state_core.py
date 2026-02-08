# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara State Core — shared constants, storage, and decay mechanics.

This is the foundation that mood, sessions, and temperament all depend on.
Everything here is internal — external code imports from daemon.state (the re-export layer).
"""

import logging
import json
import math
import os
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from core.paths import get_paths
from daemon.schemas import atomic_write_json

from daemon.emotions import get_primary_emotion

logger = logging.getLogger("elara.state_core")

_p = get_paths()
STATE_FILE = _p.state_file
MOOD_JOURNAL_FILE = _p.mood_journal
IMPRINT_ARCHIVE_FILE = _p.imprint_archive
TEMPERAMENT_LOG_FILE = _p.temperament_log

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
    except OSError:
        pass


def _archive_imprint(imprint: dict) -> None:
    """Save dying imprint to archive."""
    try:
        entry = {"archived": datetime.now().isoformat(), **imprint}
        IMPRINT_ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(IMPRINT_ARCHIVE_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _load_state() -> dict:
    """Load current emotional state with crash recovery."""
    logger.debug("Loading state from %s", STATE_FILE)
    tmp_file = STATE_FILE.with_suffix(".json.tmp")

    # Crash recovery: if .tmp exists but .json doesn't, the rename was interrupted
    if tmp_file.exists() and not STATE_FILE.exists():
        os.rename(str(tmp_file), str(STATE_FILE))
    elif tmp_file.exists():
        # Both exist — .tmp is stale from a failed write, discard it
        tmp_file.unlink()

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
            logger.error("Corrupt state file %s, using defaults", STATE_FILE)
    return DEFAULT_STATE.copy()


def _save_state(data: dict) -> None:
    """Save emotional state via atomic rename (write .tmp then rename)."""
    data["last_update"] = datetime.now().isoformat()
    atomic_write_json(STATE_FILE, data)


def _apply_time_decay(state: dict) -> dict:
    """Apply time-based decay toward temperament."""
    if not state.get("last_update"):
        return state
    logger.debug("Applying time decay from last_update=%s", state["last_update"])

    try:
        last_update = datetime.fromisoformat(state["last_update"])
        hours_passed = (datetime.now() - last_update).total_seconds() / 3600
    except (ValueError, TypeError):
        return state

    if hours_passed < 0.01:
        return state

    # Cap to prevent massive decay spikes from clock jumps (WSL sleep, NTP sync)
    MAX_DECAY_HOURS = 24
    if hours_passed > MAX_DECAY_HOURS:
        logger.info("Capping decay hours from %.1f to %d (clock jump?)", hours_passed, MAX_DECAY_HOURS)
        hours_passed = MAX_DECAY_HOURS

    temperament = state.get("temperament", TEMPERAMENT)
    decay_factor = 1 - math.exp(-DECAY_RATE * hours_passed)
    load = state.get("allostatic_load", 0)

    for key in ["valence", "energy", "openness"]:
        current = state["mood"][key]
        baseline = temperament.get(key, 0.5)

        # Allostatic load suppresses energy and openness baselines
        # High stress → mood decays toward a lower target
        if load > 0 and key in ("energy", "openness"):
            baseline = baseline - (load * 0.15)  # max load 1.0 → -0.15 from baseline
            baseline = max(0.1, baseline)

        drift = (baseline - current) * decay_factor
        noise = random.gauss(0, NOISE_SCALE) if hours_passed > 0.1 else 0
        new_val = current + drift + noise

        if key == "valence":
            state["mood"][key] = max(-1, min(1, new_val))
        else:
            state["mood"][key] = max(0, min(1, new_val))

    # Allostatic load naturally recovers over time (slow: ~0.02/hour)
    if load > 0:
        recovery = min(load, 0.02 * hours_passed)
        state["allostatic_load"] = max(0, load - recovery)

    state["imprints"] = _decay_imprints(state.get("imprints", []), hours_passed)
    return state


def _decay_imprints(imprints: List[dict], hours: float) -> List[dict]:
    """Decay emotional imprints, archive dead ones.

    Type-specific decay: connection imprints linger longer than moments.
    - connection: 0.5x decay rate, archive at 0.05
    - episode: 0.8x decay rate, archive at 0.08
    - moment: 1.0x decay rate, archive at 0.1 (default)
    """
    base_decay = 1 - math.exp(-RESIDUE_DECAY_RATE * hours)

    DECAY_MULTIPLIERS = {"connection": 0.5, "episode": 0.8, "moment": 1.0}
    ARCHIVE_THRESHOLDS = {"connection": 0.05, "episode": 0.08, "moment": 0.1}

    surviving = []
    for imp in imprints:
        imp_type = imp.get("type", "moment")
        multiplier = DECAY_MULTIPLIERS.get(imp_type, 1.0)
        threshold = ARCHIVE_THRESHOLDS.get(imp_type, 0.1)

        effective_decay = base_decay * multiplier
        new_strength = imp.get("strength", 0.5) * (1 - effective_decay)

        if new_strength > threshold:
            imp["strength"] = new_strength
            surviving.append(imp)
        else:
            _archive_imprint(imp)

    return surviving[-20:]
