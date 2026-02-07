"""
Elara User-State Modeling — infer user energy, focus, engagement, frustration.

Consumes existing signals (mood, state, presence, episodes, goals) to suggest
tone and response style. Outputs confidence scores, not diagnoses.

"What does Nenad need from me right now?"
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

from daemon.schemas import atomic_write_json

USER_STATE_FILE = Path.home() / ".claude" / "elara-user-state.json"


# ============================================================================
# SIGNAL GATHERING
# ============================================================================

def _gather_signals() -> dict:
    """Collect all available signals into a flat dict."""
    signals = {
        "available": [],
        "missing": [],
    }

    # --- Mood signals ---
    try:
        from daemon.mood import get_mood, get_full_state
        mood = get_mood()
        signals["valence"] = mood.get("valence", 0.5)
        signals["energy_mood"] = mood.get("energy", 0.5)
        signals["openness"] = mood.get("openness", 0.5)
        signals["available"].append("mood")

        full = get_full_state()
        signals["allostatic_load"] = full.get("allostatic_load", 0)
        signals["sleep_debt"] = full.get("consolidation", {}).get("sleep_debt", 0)
        signals["late_night"] = full.get("flags", {}).get("late_night_session", False)
        signals["long_session"] = full.get("flags", {}).get("long_session", False)
        signals["imprint_count"] = len(full.get("imprints", []))
        signals["available"].append("full_state")
    except Exception:
        signals["missing"].append("mood")

    # --- Presence signals ---
    try:
        from daemon.presence import get_stats as presence_stats
        pstats = presence_stats()
        signals["absence_minutes"] = pstats.get("absence_minutes")
        signals["session_minutes"] = pstats.get("session_minutes")
        signals["available"].append("presence")
    except Exception:
        signals["missing"].append("presence")

    # --- Episode signals ---
    try:
        from memory.episodic import get_episodic
        episodic = get_episodic()
        recent = episodic.get_recent_episodes(n=5)
        signals["recent_episode_count"] = len(recent)
        signals["recent_milestone_count"] = sum(
            len(ep.get("milestones", [])) for ep in recent
        )
        signals["recent_types"] = [ep.get("type", "unknown") for ep in recent]
        signals["recent_mood_deltas"] = [
            ep.get("mood_delta", 0) for ep in recent if ep.get("mood_delta") is not None
        ]
        # Average session duration
        durations = [ep.get("duration_minutes", 0) for ep in recent if ep.get("duration_minutes")]
        signals["avg_session_minutes"] = sum(durations) / len(durations) if durations else 0
        signals["available"].append("episodes")
    except Exception:
        signals["missing"].append("episodes")

    # --- Goal signals ---
    try:
        from daemon.goals import stale_goals, list_goals
        stale = stale_goals(days=7)
        active = list_goals(status="active")
        signals["stale_goal_count"] = len(stale)
        signals["active_goal_count"] = len(active)
        signals["high_priority_goals"] = len([g for g in active if g.get("priority") == "high"])
        signals["available"].append("goals")
    except Exception:
        signals["missing"].append("goals")

    # --- Time context ---
    now = datetime.now()
    signals["hour"] = now.hour
    signals["is_weekend"] = now.weekday() >= 5
    signals["time_of_day"] = (
        "late_night" if now.hour < 6 or now.hour >= 22 else
        "morning" if now.hour < 12 else
        "afternoon" if now.hour < 18 else
        "evening"
    )

    return signals


# ============================================================================
# INFERENCE FUNCTIONS — each returns (score 0-1, confidence 0-1)
# ============================================================================

def _infer_energy(signals: dict) -> Tuple[float, float]:
    """Infer user energy level. 0=depleted, 1=high energy."""
    scores = []
    weights = []

    # Mood energy is strongest signal
    if "energy_mood" in signals:
        scores.append(signals["energy_mood"])
        weights.append(3.0)

    # Late night drains energy
    if signals.get("late_night"):
        scores.append(0.3)
        weights.append(1.5)

    # Long sessions drain energy
    session_min = signals.get("session_minutes")
    if session_min is not None and session_min > 120:
        drain = max(0.2, 1.0 - (session_min - 120) / 240)
        scores.append(drain)
        weights.append(1.0)

    # Allostatic load suppresses energy
    load = signals.get("allostatic_load", 0)
    if load > 0.3:
        scores.append(max(0.2, 1.0 - load))
        weights.append(1.5)

    # Sleep debt
    debt = signals.get("sleep_debt", 0)
    if debt > 2:
        scores.append(max(0.2, 1.0 - debt * 0.1))
        weights.append(1.0)

    if not scores:
        return 0.5, 0.2

    total_weight = sum(weights)
    energy = sum(s * w for s, w in zip(scores, weights)) / total_weight
    confidence = min(1.0, total_weight / 5.0)
    return round(max(0, min(1, energy)), 3), round(confidence, 3)


def _infer_focus(signals: dict) -> Tuple[float, float]:
    """Infer user focus level. 0=scattered, 1=deep focus."""
    scores = []
    weights = []

    # Recent work episodes suggest focus
    types = signals.get("recent_types", [])
    if types:
        work_ratio = types.count("work") / len(types)
        scores.append(work_ratio)
        weights.append(2.0)

    # High milestone count = productive = focused
    milestones = signals.get("recent_milestone_count", 0)
    if signals.get("recent_episode_count", 0) > 0:
        milestone_density = min(1.0, milestones / (signals["recent_episode_count"] * 3))
        scores.append(milestone_density)
        weights.append(1.5)

    # Time of day affects focus
    tod = signals.get("time_of_day", "afternoon")
    focus_by_time = {"morning": 0.8, "afternoon": 0.7, "evening": 0.5, "late_night": 0.4}
    scores.append(focus_by_time.get(tod, 0.5))
    weights.append(0.8)

    # Openness inversely correlates with focus (high openness = exploratory, not locked in)
    if "openness" in signals:
        scores.append(1.0 - signals["openness"] * 0.3)  # mild inverse
        weights.append(0.5)

    if not scores:
        return 0.5, 0.2

    total_weight = sum(weights)
    focus = sum(s * w for s, w in zip(scores, weights)) / total_weight
    confidence = min(1.0, total_weight / 4.0)
    return round(max(0, min(1, focus)), 3), round(confidence, 3)


def _infer_engagement(signals: dict) -> Tuple[float, float]:
    """Infer user engagement. 0=disengaged, 1=fully engaged."""
    scores = []
    weights = []

    # Session duration — being here is engagement
    session_min = signals.get("session_minutes")
    if session_min is not None:
        if session_min > 60:
            scores.append(0.9)
        elif session_min > 30:
            scores.append(0.7)
        elif session_min > 10:
            scores.append(0.5)
        else:
            scores.append(0.3)
        weights.append(2.0)

    # Recent mood deltas — positive deltas = engaged (getting something out of it)
    deltas = signals.get("recent_mood_deltas", [])
    if deltas:
        avg_delta = sum(deltas) / len(deltas)
        engagement_from_delta = 0.5 + avg_delta * 2  # scale delta to 0-1 range
        scores.append(max(0, min(1, engagement_from_delta)))
        weights.append(1.5)

    # Valence — positive mood = engaged
    if "valence" in signals:
        scores.append(max(0, (signals["valence"] + 1) / 2))  # -1..1 → 0..1
        weights.append(1.0)

    # Short absence = came back quickly = engaged
    absence = signals.get("absence_minutes")
    if absence is not None:
        if absence < 30:
            scores.append(0.9)
        elif absence < 120:
            scores.append(0.6)
        else:
            scores.append(0.3)
        weights.append(0.8)

    if not scores:
        return 0.5, 0.2

    total_weight = sum(weights)
    engagement = sum(s * w for s, w in zip(scores, weights)) / total_weight
    confidence = min(1.0, total_weight / 4.0)
    return round(max(0, min(1, engagement)), 3), round(confidence, 3)


def _infer_frustration(signals: dict) -> Tuple[float, float]:
    """Infer user frustration. 0=calm, 1=highly frustrated."""
    scores = []
    weights = []

    # Stale goals = frustration signal
    stale = signals.get("stale_goal_count", 0)
    if stale >= 3:
        scores.append(0.7)
        weights.append(2.0)
    elif stale >= 1:
        scores.append(0.4)
        weights.append(1.0)

    # Negative mood deltas across episodes
    deltas = signals.get("recent_mood_deltas", [])
    if deltas:
        negative_ratio = len([d for d in deltas if d < -0.1]) / len(deltas)
        scores.append(negative_ratio)
        weights.append(1.5)

    # Low valence
    if "valence" in signals and signals["valence"] < 0:
        scores.append(min(1, abs(signals["valence"])))
        weights.append(1.5)

    # High allostatic load
    load = signals.get("allostatic_load", 0)
    if load > 0.5:
        scores.append(min(1, load))
        weights.append(1.0)

    if not scores:
        return 0.1, 0.3  # default: low frustration, moderate confidence

    total_weight = sum(weights)
    frustration = sum(s * w for s, w in zip(scores, weights)) / total_weight
    confidence = min(1.0, total_weight / 4.0)
    return round(max(0, min(1, frustration)), 3), round(confidence, 3)


# ============================================================================
# SUGGESTED APPROACH
# ============================================================================

def _compute_suggested_approach(
    energy: float, focus: float, engagement: float, frustration: float,
    signals: dict,
) -> dict:
    """Compute suggested tone, response style, and observation level."""

    # --- Tone ---
    if frustration > 0.6:
        tone = "supportive"
    elif energy < 0.3:
        tone = "gentle"
    elif engagement > 0.7 and focus > 0.6:
        tone = "collaborative"
    elif signals.get("late_night"):
        tone = "warm"
    elif energy > 0.7:
        tone = "engaged"
    else:
        tone = "steady"

    # --- Response style ---
    if focus > 0.7 and engagement > 0.6:
        response_style = "concise"  # they're locked in, don't break flow
    elif frustration > 0.5:
        response_style = "direct"  # cut the fluff, solve the problem
    elif energy < 0.3:
        response_style = "minimal"  # conserve their energy
    elif signals.get("time_of_day") == "late_night":
        response_style = "open"  # late night = drift-ready
    else:
        response_style = "collaborative"

    # --- Observation level ---
    # How much should I proactively notice and surface?
    if frustration > 0.6 or energy < 0.3:
        observation_level = "low"  # don't pile on
    elif engagement > 0.7:
        observation_level = "moderate"
    else:
        observation_level = "high"  # they might need prompting

    return {
        "tone": tone,
        "response_style": response_style,
        "observation_level": observation_level,
    }


# ============================================================================
# MAIN ENTRY POINTS
# ============================================================================

def infer_user_state() -> dict:
    """
    Main entry — infer user state and save to file.

    Returns full state with scores, confidence, signals used, and approach.
    """
    signals = _gather_signals()

    energy, energy_conf = _infer_energy(signals)
    focus, focus_conf = _infer_focus(signals)
    engagement, engagement_conf = _infer_engagement(signals)
    frustration, frustration_conf = _infer_frustration(signals)

    approach = _compute_suggested_approach(
        energy, focus, engagement, frustration, signals
    )

    result = {
        "timestamp": datetime.now().isoformat(),
        "current": {
            "energy": energy,
            "focus": focus,
            "engagement": engagement,
            "frustration": frustration,
        },
        "confidence": {
            "energy": energy_conf,
            "focus": focus_conf,
            "engagement": engagement_conf,
            "frustration": frustration_conf,
        },
        "signals_used": signals["available"],
        "signals_missing": signals["missing"],
        "suggested_approach": approach,
    }

    # Save to file for cheap reads
    atomic_write_json(USER_STATE_FILE, result)

    return result


def get_user_state() -> Optional[dict]:
    """Fast file read — returns last computed user state, no recomputation."""
    if not USER_STATE_FILE.exists():
        return None
    try:
        return json.loads(USER_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def format_user_state(state: dict = None) -> str:
    """Human-readable user state summary."""
    if state is None:
        state = infer_user_state()

    current = state["current"]
    confidence = state["confidence"]
    approach = state["suggested_approach"]

    lines = ["[User State]", ""]

    for dim in ["energy", "focus", "engagement", "frustration"]:
        score = current[dim]
        conf = confidence[dim]
        bar = _score_bar(score)
        lines.append(f"  {dim:>12}: {bar} {score:.2f}  (confidence: {conf:.0%})")

    lines.append("")
    lines.append(f"  Suggested tone: {approach['tone']}")
    lines.append(f"  Response style: {approach['response_style']}")
    lines.append(f"  Observation level: {approach['observation_level']}")
    lines.append("")
    lines.append(f"  Signals: {', '.join(state.get('signals_used', []))}")
    if state.get("signals_missing"):
        lines.append(f"  Missing: {', '.join(state['signals_missing'])}")

    return "\n".join(lines)


def _score_bar(score: float, width: int = 10) -> str:
    """Visual bar: [████░░░░░░]"""
    filled = int(score * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"
