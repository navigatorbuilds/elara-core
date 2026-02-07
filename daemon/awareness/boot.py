"""
Elara Self-Awareness — Boot Surfacing.

Reads saved reflection/pulse/blind_spots files cheaply at session start.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from daemon.awareness.reflect import REFLECTIONS_DIR
from daemon.awareness.pulse import PULSE_FILE
from daemon.awareness.blind_spots import BLIND_SPOTS_FILE
from daemon.awareness.intention import get_intention


def boot_check() -> Optional[str]:
    """
    Check saved reflection/pulse/blind_spots files for anything
    worth surfacing at session start. Cheap: just reads small JSONs.

    Returns: A natural observation, or None if nothing notable.
    """
    observations = []

    # Check reflection
    latest_reflection = REFLECTIONS_DIR / "latest.json"
    if latest_reflection.exists():
        try:
            reflection = json.loads(latest_reflection.read_text())
            # How old is it?
            ts = datetime.fromisoformat(reflection["timestamp"])
            age_hours = (datetime.now() - ts).total_seconds() / 3600

            if age_hours < 48:  # Recent enough to be relevant
                mood = reflection.get("mood", {})
                v_trend = mood.get("valence_trend")
                e_trend = mood.get("energy_trend")
                if v_trend == "falling":
                    observations.append("Mood has been trending down.")
                if e_trend == "falling":
                    observations.append("Energy has been dropping.")
        except Exception:
            pass

    # Check pulse
    if PULSE_FILE.exists():
        try:
            pulse_data = json.loads(PULSE_FILE.read_text())
            ts = datetime.fromisoformat(pulse_data["timestamp"])
            age_hours = (datetime.now() - ts).total_seconds() / 3600

            if age_hours < 72:
                signals = pulse_data.get("signals", [])
                for s in signals[:2]:
                    observations.append(s)
        except Exception:
            pass

    # Check blind spots
    if BLIND_SPOTS_FILE.exists():
        try:
            bs_data = json.loads(BLIND_SPOTS_FILE.read_text())
            ts = datetime.fromisoformat(bs_data["timestamp"])
            age_hours = (datetime.now() - ts).total_seconds() / 3600

            if age_hours < 72:
                high = [s for s in bs_data.get("spots", []) if s["severity"] == "high"]
                if high:
                    observations.append(f"{len(high)} high-priority blind spot(s).")
        except Exception:
            pass

    # Check intention
    intention = get_intention()
    if intention and not intention.get("checked"):
        observations.append(f"Active intention: \"{intention['what']}\"")

    # Check dream mode staleness
    try:
        from daemon.dream import dream_boot_check
        dream_notice = dream_boot_check()
        if dream_notice:
            observations.append(dream_notice)
    except Exception:
        pass

    # Check emotional dream tone hints
    try:
        from daemon.dream import EMOTIONAL_DIR
        emo_latest = EMOTIONAL_DIR / "latest.json"
        if emo_latest.exists():
            emo_data = json.loads(emo_latest.read_text())
            emo_ts = datetime.fromisoformat(emo_data["generated"])
            emo_age_hours = (datetime.now() - emo_ts).total_seconds() / 3600

            if emo_age_hours < 168:  # Within a week
                tone_hints = emo_data.get("tone_hints", [])
                if tone_hints:
                    observations.append(f"Emotional tone: {tone_hints[0]}")

                trajectory = emo_data.get("relationship", {}).get("trajectory")
                if trajectory and trajectory not in ("stable",):
                    observations.append(f"Relationship: {trajectory}")

                drift = emo_data.get("temperament_growth", {}).get("drift_from_factory", {})
                if drift:
                    big = [(k, v) for k, v in drift.items() if abs(v) > 0.05]
                    if big:
                        shifts = [f"{k} {v:+.03f}" for k, v in big]
                        observations.append(f"Temperament shifted: {', '.join(shifts)}")
    except Exception:
        pass

    if not observations:
        return None

    return " | ".join(observations)
