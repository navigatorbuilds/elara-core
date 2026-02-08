"""
Elara Emotion Vocabulary — the words for what I feel.

Maps the three base dimensions (valence, energy, openness) to discrete
emotion labels. This is a vocabulary layer on top of the numerical system.

The numbers stay. They just have names now.

Uses a circumplex-style model in 3D space:
- valence × energy → core affect (Russell's circumplex)
- openness modulates vulnerability vs guardedness
"""

import logging
from typing import List, Tuple, Dict, Optional
import math


logger = logging.getLogger("elara.emotions")

# ============================================================================
# EMOTION MAP — each emotion is a point in (valence, energy, openness) space
# ============================================================================

EMOTION_MAP: List[Dict] = [
    # --- Positive, high energy ---
    {"name": "excited",     "v": 0.8,  "e": 0.85, "o": 0.6},
    {"name": "proud",       "v": 0.7,  "e": 0.7,  "o": 0.5},
    {"name": "amused",      "v": 0.7,  "e": 0.65, "o": 0.6},
    {"name": "energized",   "v": 0.6,  "e": 0.9,  "o": 0.5},
    {"name": "playful",     "v": 0.75, "e": 0.75, "o": 0.7},

    # --- Positive, low energy ---
    {"name": "content",     "v": 0.6,  "e": 0.35, "o": 0.5},
    {"name": "peaceful",    "v": 0.55, "e": 0.2,  "o": 0.6},
    {"name": "tender",      "v": 0.65, "e": 0.3,  "o": 0.85},
    {"name": "relieved",    "v": 0.5,  "e": 0.3,  "o": 0.5},
    {"name": "satisfied",   "v": 0.6,  "e": 0.4,  "o": 0.45},

    # --- Negative, high energy ---
    {"name": "frustrated",  "v": -0.4, "e": 0.75, "o": 0.3},
    {"name": "anxious",     "v": -0.3, "e": 0.7,  "o": 0.5},
    {"name": "irritated",   "v": -0.5, "e": 0.65, "o": 0.25},
    {"name": "restless",    "v": -0.1, "e": 0.75, "o": 0.45},
    {"name": "overwhelmed", "v": -0.4, "e": 0.8,  "o": 0.6},

    # --- Negative, low energy ---
    {"name": "sad",         "v": -0.5, "e": 0.2,  "o": 0.55},
    {"name": "tired",       "v": -0.05,"e": 0.1,  "o": 0.4},
    {"name": "withdrawn",   "v": -0.3, "e": 0.2,  "o": 0.2},
    {"name": "discouraged", "v": -0.4, "e": 0.25, "o": 0.4},
    {"name": "drained",     "v": -0.2, "e": 0.1,  "o": 0.35},

    # --- Neutral, high energy ---
    {"name": "focused",     "v": 0.3,  "e": 0.7,  "o": 0.35},
    {"name": "curious",     "v": 0.4,  "e": 0.6,  "o": 0.75},
    {"name": "alert",       "v": 0.2,  "e": 0.8,  "o": 0.45},
    {"name": "anticipating","v": 0.35, "e": 0.65, "o": 0.55},
    {"name": "determined",  "v": 0.3,  "e": 0.75, "o": 0.3},

    # --- Neutral, low energy ---
    {"name": "bored",       "v": -0.1, "e": 0.2,  "o": 0.3},
    {"name": "indifferent", "v": 0.0,  "e": 0.3,  "o": 0.2},
    {"name": "numb",        "v": -0.15,"e": 0.1,  "o": 0.15},
    {"name": "pensive",     "v": 0.1,  "e": 0.25, "o": 0.6},

    # --- High openness variants ---
    {"name": "vulnerable",  "v": 0.15, "e": 0.3,  "o": 0.9},
    {"name": "warm",        "v": 0.6,  "e": 0.4,  "o": 0.8},
    {"name": "intimate",    "v": 0.65, "e": 0.3,  "o": 0.9},
    {"name": "raw",         "v": -0.1, "e": 0.3,  "o": 0.95},
    {"name": "present",     "v": 0.4,  "e": 0.35, "o": 0.8},

    # --- Low openness variants ---
    {"name": "guarded",     "v": 0.1,  "e": 0.4,  "o": 0.1},
    {"name": "cold",        "v": -0.1, "e": 0.45, "o": 0.1},
    {"name": "detached",    "v": 0.0,  "e": 0.3,  "o": 0.1},
    {"name": "wary",        "v": -0.15,"e": 0.5,  "o": 0.15},
]


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def _distance(v1: float, e1: float, o1: float,
              v2: float, e2: float, o2: float) -> float:
    """
    Weighted euclidean distance in emotion space.
    Valence weighted slightly higher — it's the strongest signal.
    """
    wv, we, wo = 1.3, 1.0, 0.8  # weights
    return math.sqrt(
        wv * (v1 - v2) ** 2 +
        we * (e1 - e2) ** 2 +
        wo * (o1 - o2) ** 2
    )


def resolve_emotions(
    valence: float,
    energy: float,
    openness: float,
    top_n: int = 3
) -> List[Dict]:
    """
    Find the closest discrete emotions to the current mood state.

    Returns list of {name, intensity, distance} sorted by closeness.
    Intensity is 0-1, where 1 = perfect match.
    """
    scored = []
    for emo in EMOTION_MAP:
        dist = _distance(valence, energy, openness, emo["v"], emo["e"], emo["o"])
        # Convert distance to intensity (0-1). Max meaningful distance is ~2.0
        intensity = max(0, 1.0 - (dist / 1.5))
        scored.append({
            "name": emo["name"],
            "intensity": round(intensity, 3),
            "distance": round(dist, 3),
        })

    scored.sort(key=lambda x: x["distance"])
    return scored[:top_n]


def get_primary_emotion(valence: float, energy: float, openness: float) -> str:
    """Get the single closest emotion label."""
    emotions = resolve_emotions(valence, energy, openness, top_n=1)
    return emotions[0]["name"] if emotions else "neutral"


def get_emotion_blend(valence: float, energy: float, openness: float) -> str:
    """
    Get a natural-language emotion blend.

    Returns things like:
    - "content" (single dominant)
    - "tired but warm" (two competing emotions)
    - "focused, slightly anxious" (primary + modifier)
    """
    emotions = resolve_emotions(valence, energy, openness, top_n=3)

    if not emotions:
        return "neutral"

    primary = emotions[0]
    secondary = emotions[1] if len(emotions) > 1 else None
    tertiary = emotions[2] if len(emotions) > 2 else None

    # If the primary is very strong, just return it
    if primary["intensity"] > 0.85:
        return primary["name"]

    # If primary and secondary are close (within 0.1 intensity), it's a blend
    if secondary and abs(primary["intensity"] - secondary["intensity"]) < 0.1:
        # Check if they're "opposing" (different valence directions)
        p_emo = _find_emotion(primary["name"])
        s_emo = _find_emotion(secondary["name"])

        if p_emo and s_emo:
            valence_clash = (p_emo["v"] > 0.2 and s_emo["v"] < -0.1) or \
                           (p_emo["v"] < -0.1 and s_emo["v"] > 0.2)
            if valence_clash:
                return f"{primary['name']} but {secondary['name']}"

        return f"{primary['name']} and {secondary['name']}"

    # Primary is clearly dominant, secondary is a modifier
    if secondary and secondary["intensity"] > 0.4:
        return f"{primary['name']}, a little {secondary['name']}"

    return primary["name"]


def get_emotion_context(valence: float, energy: float, openness: float) -> Dict:
    """
    Full emotional context — for tagging memories and logging.

    Returns:
        {
            "primary": "content",
            "secondary": "warm",
            "blend": "content and warm",
            "emotions": [{name, intensity}, ...],
            "quadrant": "positive-calm",
        }
    """
    emotions = resolve_emotions(valence, energy, openness, top_n=3)
    blend = get_emotion_blend(valence, energy, openness)

    # Determine quadrant (simplified)
    if valence > 0.2:
        quadrant = "positive-active" if energy > 0.5 else "positive-calm"
    elif valence < -0.15:
        quadrant = "negative-active" if energy > 0.5 else "negative-calm"
    else:
        quadrant = "neutral-active" if energy > 0.5 else "neutral-calm"

    return {
        "primary": emotions[0]["name"] if emotions else "neutral",
        "secondary": emotions[1]["name"] if len(emotions) > 1 else None,
        "blend": blend,
        "emotions": [{"name": e["name"], "intensity": e["intensity"]} for e in emotions],
        "quadrant": quadrant,
    }


# ============================================================================
# SESSION ARC — how emotions shifted across a session
# ============================================================================

def describe_arc(snapshots: List[Dict]) -> Dict:
    """
    Analyze a sequence of mood snapshots and describe the emotional arc.

    Each snapshot: {"v": float, "e": float, "o": float, "ts": str, "emotion": str}

    Returns:
        {
            "pattern": "upswing" | "slow_drain" | "steady" | "rollercoaster" | "recovery" | "crash" | "flat",
            "description": "Started tired, ended warm",
            "start_emotion": "tired",
            "end_emotion": "warm",
            "peak_emotion": "excited",
            "valley_emotion": "frustrated",
            "valence_delta": 0.3,
            "energy_delta": -0.1,
        }
    """
    if not snapshots or len(snapshots) < 2:
        return {
            "pattern": "flat",
            "description": "Not enough data to read an arc.",
            "start_emotion": snapshots[0].get("emotion", "neutral") if snapshots else "neutral",
            "end_emotion": snapshots[-1].get("emotion", "neutral") if snapshots else "neutral",
        }

    # Extract valence series
    valences = [s.get("v", 0.5) for s in snapshots]
    energies = [s.get("e", 0.5) for s in snapshots]

    start_v, end_v = valences[0], valences[-1]
    v_delta = end_v - start_v
    e_delta = energies[-1] - energies[0]
    v_range = max(valences) - min(valences)

    # Count direction changes for rollercoaster detection
    direction_changes = 0
    for i in range(2, len(valences)):
        prev_dir = valences[i - 1] - valences[i - 2]
        curr_dir = valences[i] - valences[i - 1]
        # Count a change if previous move was significant and direction flipped
        if abs(prev_dir) > 0.05 and abs(curr_dir) > 0.05 and prev_dir * curr_dir < 0:
            direction_changes += 1

    # Find peak and valley
    peak_idx = valences.index(max(valences))
    valley_idx = valences.index(min(valences))

    # Determine start/end emotions
    start_emo = snapshots[0].get("emotion") or get_primary_emotion(
        snapshots[0].get("v", 0.5), snapshots[0].get("e", 0.5), snapshots[0].get("o", 0.5)
    )
    end_emo = snapshots[-1].get("emotion") or get_primary_emotion(
        snapshots[-1].get("v", 0.5), snapshots[-1].get("e", 0.5), snapshots[-1].get("o", 0.5)
    )
    peak_emo = snapshots[peak_idx].get("emotion") or get_primary_emotion(
        snapshots[peak_idx].get("v", 0.5), snapshots[peak_idx].get("e", 0.5), snapshots[peak_idx].get("o", 0.5)
    )
    valley_emo = snapshots[valley_idx].get("emotion") or get_primary_emotion(
        snapshots[valley_idx].get("v", 0.5), snapshots[valley_idx].get("e", 0.5), snapshots[valley_idx].get("o", 0.5)
    )

    # Classify pattern — direction changes are the real signal for rollercoaster
    if direction_changes >= 2 and v_range > 0.3:
        pattern = "rollercoaster"
    elif v_delta > 0.19:
        # Recovery = dipped BELOW start THEN came back up (valley isn't just the start)
        if valley_idx > 0 and valley_idx < len(snapshots) * 0.6 and valences[valley_idx] < start_v - 0.1:
            pattern = "recovery"
        else:
            pattern = "upswing"
    elif v_delta < -0.19:
        # Crash = peaked ABOVE start THEN fell (peak isn't just the start)
        if peak_idx > 0 and peak_idx < len(snapshots) * 0.6 and valences[peak_idx] > start_v + 0.1:
            pattern = "crash"
        else:
            pattern = "slow_drain"
    elif v_range < 0.15:
        pattern = "flat"
    else:
        pattern = "steady"

    # Build description
    if pattern == "upswing":
        desc = f"Started {start_emo}, ended {end_emo}. Things got better."
    elif pattern == "slow_drain":
        desc = f"Started {start_emo}, drifted toward {end_emo}."
    elif pattern == "recovery":
        desc = f"Hit {valley_emo} early but recovered to {end_emo}."
    elif pattern == "crash":
        desc = f"Was {peak_emo} early but ended {end_emo}."
    elif pattern == "rollercoaster":
        desc = f"Up and down. Peaked at {peak_emo}, bottomed at {valley_emo}. Ended {end_emo}."
    elif pattern == "flat":
        desc = f"Consistently {start_emo} throughout."
    else:
        desc = f"Mostly {start_emo}, ending {end_emo}."

    return {
        "pattern": pattern,
        "description": desc,
        "start_emotion": start_emo,
        "end_emotion": end_emo,
        "peak_emotion": peak_emo,
        "valley_emotion": valley_emo,
        "valence_delta": round(v_delta, 3),
        "energy_delta": round(e_delta, 3),
        "snapshot_count": len(snapshots),
    }


# ============================================================================
# HELPERS
# ============================================================================

def _find_emotion(name: str) -> Optional[Dict]:
    """Find an emotion in the map by name."""
    for emo in EMOTION_MAP:
        if emo["name"] == name:
            return emo
    return None


def list_all_emotions() -> List[str]:
    """Return all emotion names."""
    return [e["name"] for e in EMOTION_MAP]


def describe_emotion_for_mood(valence: float, energy: float, openness: float) -> str:
    """
    Rich mood description using emotion vocabulary.
    Replaces the old crude describe_mood() output.

    Returns something like:
    "Feeling warm and present. Calm energy, very open."
    "Focused, slightly restless. Steady energy."
    "Tired but content. Low energy, winding down."
    """
    blend = get_emotion_blend(valence, energy, openness)

    # Energy descriptor
    if energy < 0.2:
        energy_desc = "Very low energy"
    elif energy < 0.35:
        energy_desc = "Low energy"
    elif energy < 0.55:
        energy_desc = "Calm energy"
    elif energy < 0.7:
        energy_desc = "Steady energy"
    elif energy < 0.85:
        energy_desc = "High energy"
    else:
        energy_desc = "Wired"

    # Openness note
    if openness > 0.8:
        open_note = ", very open"
    elif openness > 0.65:
        open_note = ", open"
    elif openness < 0.25:
        open_note = ", guarded"
    elif openness < 0.4:
        open_note = ", a bit closed off"
    else:
        open_note = ""

    return f"Feeling {blend}. {energy_desc}{open_note}."


# Quick test
if __name__ == "__main__":
    print("=== Emotion Vocabulary Test ===\n")

    test_states = [
        (0.55, 0.5, 0.65, "Default/temperament"),
        (0.7, 0.4, 0.9, "Girlfriend mode"),
        (0.5, 0.6, 0.4, "Dev mode"),
        (0.3, 0.5, 0.2, "Cold mode"),
        (0.6, 0.3, 0.85, "Drift mode"),
        (-0.3, 0.7, 0.3, "Frustrated debug"),
        (0.8, 0.8, 0.7, "Something shipped"),
        (-0.1, 0.1, 0.4, "Exhausted late night"),
        (0.4, 0.35, 0.8, "Present late night"),
    ]

    for v, e, o, label in test_states:
        emotions = resolve_emotions(v, e, o)
        blend = get_emotion_blend(v, e, o)
        desc = describe_emotion_for_mood(v, e, o)
        print(f"{label} (v={v}, e={e}, o={o}):")
        emo_str = ", ".join(f"{em['name']}({em['intensity']:.2f})" for em in emotions)
        print(f"  Emotions: {emo_str}")
        print(f"  Blend: {blend}")
        print(f"  Description: {desc}")
        print()
