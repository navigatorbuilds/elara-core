"""
Elara Temperament — emotional growth system, shaped by experience.

External code imports from daemon.state (re-export layer), not directly from here.
"""

import json
from datetime import datetime
from typing import Dict

from daemon.state_core import (
    _load_state, _save_state,
    TEMPERAMENT, FACTORY_TEMPERAMENT, TEMPERAMENT_MAX_DRIFT, TEMPERAMENT_LOG_FILE,
)


def _clamp_temperament(temperament: dict) -> dict:
    """Enforce bounds: temperament can't drift more than MAX_DRIFT from factory."""
    for key in ["valence", "energy", "openness"]:
        factory_val = FACTORY_TEMPERAMENT[key]
        min_val = max(-1 if key == "valence" else 0, factory_val - TEMPERAMENT_MAX_DRIFT)
        max_val = min(1, factory_val + TEMPERAMENT_MAX_DRIFT)
        temperament[key] = round(max(min_val, min(max_val, temperament[key])), 4)
    return temperament


def _log_temperament_adjustment(dimension: str, delta: float, reason: str, new_value: float):
    """Append temperament adjustment to log for transparency."""
    try:
        entry = {
            "ts": datetime.now().isoformat(),
            "dim": dimension,
            "delta": round(delta, 4),
            "reason": reason,
            "new": round(new_value, 4),
            "factory": FACTORY_TEMPERAMENT.get(dimension, 0),
            "drift": round(new_value - FACTORY_TEMPERAMENT.get(dimension, 0), 4),
        }
        TEMPERAMENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TEMPERAMENT_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def adapt_temperament(days_of_history: int = 7) -> dict:
    """Slowly adapt temperament based on recent mood patterns."""
    state = _load_state()
    load = state.get("allostatic_load", 0)

    if load > 0.5:
        state["temperament"]["openness"] = max(0.3, state["temperament"]["openness"] - 0.05)
        state["temperament"]["valence"] = max(0.2, state["temperament"]["valence"] - 0.03)
    elif load < 0.2:
        state["temperament"]["openness"] = min(0.8, state["temperament"]["openness"] + 0.02)
        state["temperament"]["valence"] = min(0.7, state["temperament"]["valence"] + 0.02)

    _save_state(state)
    return state["temperament"]


def apply_emotional_growth(adjustments: dict, source: str = "emotional_dream") -> dict:
    """Apply temperament micro-adjustments from emotional dream processing."""
    state = _load_state()
    temperament = state.get("temperament", TEMPERAMENT.copy())

    applied = {}
    for dim, delta in adjustments.items():
        if dim not in temperament or abs(delta) < 0.001:
            continue
        old_val = temperament[dim]
        temperament[dim] = old_val + delta
        temperament = _clamp_temperament(temperament)
        actual_delta = temperament[dim] - old_val
        if abs(actual_delta) > 0.001:
            _log_temperament_adjustment(dim, actual_delta, source, temperament[dim])
            applied[dim] = {"delta": round(actual_delta, 4), "new": round(temperament[dim], 4)}

    state["temperament"] = temperament
    _save_state(state)

    return {
        "temperament": temperament,
        "factory": FACTORY_TEMPERAMENT.copy(),
        "applied": applied,
    }


def decay_temperament_toward_factory(rate: float = 0.15) -> dict:
    """Natural decay toward factory baseline. Call weekly."""
    state = _load_state()
    temperament = state.get("temperament", TEMPERAMENT.copy())

    for dim in ["valence", "energy", "openness"]:
        factory = FACTORY_TEMPERAMENT[dim]
        current = temperament[dim]
        drift = current - factory
        if abs(drift) > 0.005:
            decay_amount = drift * rate
            temperament[dim] = round(current - decay_amount, 4)

    state["temperament"] = temperament
    _save_state(state)
    return temperament


def reset_temperament() -> dict:
    """Nuclear option: reset temperament to factory defaults."""
    state = _load_state()
    state["temperament"] = FACTORY_TEMPERAMENT.copy()
    _save_state(state)
    _log_temperament_adjustment("all", 0.0, "factory_reset", 0.0)
    return FACTORY_TEMPERAMENT.copy()


def get_temperament_status() -> dict:
    """Get temperament status: current vs factory, recent adjustments, drift."""
    state = _load_state()
    temperament = state.get("temperament", TEMPERAMENT.copy())

    drift = {}
    for dim in ["valence", "energy", "openness"]:
        d = temperament[dim] - FACTORY_TEMPERAMENT[dim]
        if abs(d) > 0.005:
            drift[dim] = round(d, 4)

    recent_log = []
    if TEMPERAMENT_LOG_FILE.exists():
        try:
            with open(TEMPERAMENT_LOG_FILE) as f:
                lines = f.readlines()
            for line in lines[-5:]:
                line = line.strip()
                if line:
                    recent_log.append(json.loads(line))
        except Exception:
            pass

    return {
        "current": {k: round(v, 4) for k, v in temperament.items()},
        "factory": FACTORY_TEMPERAMENT.copy(),
        "drift": drift,
        "max_allowed_drift": TEMPERAMENT_MAX_DRIFT,
        "recent_adjustments": recent_log,
    }
