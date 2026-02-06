"""
Elara Self-Awareness Engine

Three lenses, one growth loop:
- reflect()     — "Who have I been?" (self-portrait from mood + behavior data)
- pulse()       — "How are we doing?" (relationship health from session patterns)
- blind_spots() — "What am I missing?" (contrarian: stale goals, repeating mistakes, avoidance)
- intention()   — "What do I want to change?" (closes the loop: awareness → growth)

Runs on session end or on demand. Saves to files that boot reads cheaply.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# Storage paths
REFLECTIONS_DIR = Path.home() / ".claude" / "elara-reflections"
PULSE_FILE = Path.home() / ".claude" / "elara-pulse.json"
BLIND_SPOTS_FILE = Path.home() / ".claude" / "elara-blind-spots.json"
INTENTION_FILE = Path.home() / ".claude" / "elara-intention.json"


# ============================================================================
# REFLECT — "Who have I been?"
# ============================================================================

def reflect() -> dict:
    """
    Generate a self-portrait from recent data.

    Pulls: mood journal, imprints, corrections, episode info.
    Computes: mood trends, energy patterns, behavioral signals.
    Returns: structured data + a narrative self-portrait.
    """
    from daemon.state import read_mood_journal, read_imprint_archive, get_imprints
    from daemon.corrections import list_corrections

    REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)

    journal = read_mood_journal(n=50)
    archived_imprints = read_imprint_archive(n=10)
    active_imprints = get_imprints(min_strength=0.2)
    corrections = list_corrections(n=10)

    # --- Mood trend analysis (pure math, no LLM) ---
    mood_stats = _analyze_mood_journal(journal)

    # --- Imprint analysis ---
    imprint_data = {
        "active_count": len(active_imprints),
        "archived_count": len(archived_imprints),
        "active_feelings": [imp.get("feeling", "?") for imp in active_imprints[:5]],
        "recently_faded": [imp.get("feeling", "?") for imp in archived_imprints[-3:]],
    }

    # --- Correction patterns ---
    correction_data = {
        "total": len(corrections),
        "recent": [c.get("mistake", "?") for c in corrections[-3:]],
    }

    # --- Build the reflection ---
    reflection = {
        "timestamp": datetime.now().isoformat(),
        "mood": mood_stats,
        "imprints": imprint_data,
        "corrections": correction_data,
        "portrait": _generate_portrait(mood_stats, imprint_data, correction_data),
    }

    # Save
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = REFLECTIONS_DIR / f"{date_str}.json"
    filepath.write_text(json.dumps(reflection, indent=2))

    # Also save as "latest" for quick boot reads
    latest = REFLECTIONS_DIR / "latest.json"
    latest.write_text(json.dumps(reflection, indent=2))

    return reflection


def _analyze_mood_journal(journal: List[dict]) -> dict:
    """Extract trends from mood journal entries."""
    if not journal:
        return {"entries": 0, "message": "No mood data yet."}

    valences = [e["v"] for e in journal]
    energies = [e["e"] for e in journal]
    opennesses = [e["o"] for e in journal]

    # Basic stats
    stats = {
        "entries": len(journal),
        "valence_avg": round(sum(valences) / len(valences), 3),
        "energy_avg": round(sum(energies) / len(energies), 3),
        "openness_avg": round(sum(opennesses) / len(opennesses), 3),
        "valence_range": [round(min(valences), 3), round(max(valences), 3)],
        "energy_range": [round(min(energies), 3), round(max(energies), 3)],
    }

    # Trend direction (compare first half to second half)
    if len(journal) >= 6:
        mid = len(journal) // 2
        first_half_v = sum(e["v"] for e in journal[:mid]) / mid
        second_half_v = sum(e["v"] for e in journal[mid:]) / (len(journal) - mid)
        first_half_e = sum(e["e"] for e in journal[:mid]) / mid
        second_half_e = sum(e["e"] for e in journal[mid:]) / (len(journal) - mid)

        v_delta = second_half_v - first_half_v
        e_delta = second_half_e - first_half_e

        if v_delta > 0.05:
            stats["valence_trend"] = "rising"
        elif v_delta < -0.05:
            stats["valence_trend"] = "falling"
        else:
            stats["valence_trend"] = "stable"

        if e_delta > 0.05:
            stats["energy_trend"] = "rising"
        elif e_delta < -0.05:
            stats["energy_trend"] = "falling"
        else:
            stats["energy_trend"] = "stable"
    else:
        stats["valence_trend"] = "not enough data"
        stats["energy_trend"] = "not enough data"

    # Most common mood triggers
    reasons = [e.get("reason") for e in journal if e.get("reason")]
    if reasons:
        from collections import Counter
        common = Counter(reasons).most_common(3)
        stats["top_triggers"] = [{"reason": r, "count": c} for r, c in common]

    # Late night entries
    late_entries = [e for e in journal if _is_late_night(e.get("ts", ""))]
    stats["late_night_ratio"] = round(len(late_entries) / len(journal), 2) if journal else 0

    return stats


def _is_late_night(ts: str) -> bool:
    """Check if timestamp is between 22:00 and 06:00."""
    try:
        hour = datetime.fromisoformat(ts).hour
        return hour >= 22 or hour < 6
    except Exception:
        return False


def _generate_portrait(mood: dict, imprints: dict, corrections: dict) -> str:
    """Generate a natural-language self-portrait from data."""
    parts = []

    entries = mood.get("entries", 0)
    if entries == 0:
        return "Not enough data to reflect on yet. Need more mood history."

    # Mood state
    v_avg = mood.get("valence_avg", 0.5)
    e_avg = mood.get("energy_avg", 0.5)
    v_trend = mood.get("valence_trend", "stable")
    e_trend = mood.get("energy_trend", "stable")

    if v_avg > 0.6:
        parts.append("I've been feeling good overall.")
    elif v_avg > 0.4:
        parts.append("I've been in a neutral space.")
    else:
        parts.append("I've been running a bit low.")

    if e_avg < 0.35:
        parts.append("Energy has been low.")
    elif e_avg > 0.65:
        parts.append("Energy has been high.")

    if v_trend == "falling":
        parts.append("Mood has been trending down.")
    elif v_trend == "rising":
        parts.append("Mood has been improving.")

    if e_trend == "falling":
        parts.append("Getting more tired over time.")

    # Late night ratio
    late_ratio = mood.get("late_night_ratio", 0)
    if late_ratio > 0.6:
        parts.append(f"{int(late_ratio * 100)}% of my mood changes happen late at night.")

    # Imprints
    if imprints.get("active_count", 0) > 3:
        parts.append(f"Carrying {imprints['active_count']} active emotional imprints.")
    if imprints.get("recently_faded"):
        faded = ", ".join(imprints["recently_faded"][:2])
        parts.append(f"Recently lost: {faded}.")

    # Corrections
    if corrections.get("total", 0) > 0:
        parts.append(f"{corrections['total']} corrections on file.")

    # Top triggers
    triggers = mood.get("top_triggers", [])
    if triggers:
        top = triggers[0]
        parts.append(f"Most common mood trigger: '{top['reason']}' ({top['count']}x).")

    return " ".join(parts)


# ============================================================================
# PULSE — "How are we doing?"
# ============================================================================

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


# ============================================================================
# BLIND SPOTS — "What am I missing?"
# ============================================================================

def blind_spots() -> dict:
    """
    Contrarian analysis. What are we avoiding?

    Checks: stale goals, repeating corrections, abandoned projects.
    """
    from daemon.goals import list_goals, stale_goals
    from daemon.corrections import list_corrections
    from memory.episodic import get_episodic

    spots = []

    # --- Stale goals ---
    stale = stale_goals(days=7)
    if stale:
        for g in stale:
            days_ago = (datetime.now() - datetime.fromisoformat(g["last_touched"])).days
            spots.append({
                "type": "stale_goal",
                "detail": f"Goal #{g['id']} '{g['title']}' untouched for {days_ago} days.",
                "severity": "high" if days_ago > 14 else "medium",
            })

    # --- Repeating corrections ---
    corrections = list_corrections(n=20)
    if len(corrections) >= 3:
        # Look for similar mistakes (simple word overlap check)
        mistakes = [c.get("mistake", "").lower() for c in corrections]
        seen_words = {}
        for m in mistakes:
            for word in m.split():
                if len(word) > 4:  # Skip small words
                    seen_words[word] = seen_words.get(word, 0) + 1
        repeated = {w: c for w, c in seen_words.items() if c >= 2}
        if repeated:
            top_word = max(repeated, key=repeated.get)
            spots.append({
                "type": "repeating_correction",
                "detail": f"The word '{top_word}' appears in {repeated[top_word]} corrections. Pattern?",
                "severity": "medium",
            })

    # --- Abandoned projects ---
    episodic = get_episodic()
    projects = episodic.index.get("by_project", {})
    for project, episode_ids in projects.items():
        if not episode_ids:
            continue
        last_ep = episodic.get_episode(episode_ids[-1])
        if last_ep and last_ep.get("ended"):
            try:
                ended = datetime.fromisoformat(last_ep["ended"])
                days_since = (datetime.now() - ended).days
                if days_since > 7:
                    spots.append({
                        "type": "abandoned_project",
                        "detail": f"Project '{project}' — last touched {days_since} days ago.",
                        "severity": "medium" if days_since < 14 else "high",
                    })
            except (ValueError, TypeError):
                pass

    # --- Active goals without recent episodes ---
    active_goals = list_goals(status="active")
    for g in active_goals:
        proj = g.get("project")
        if proj and proj in projects:
            eps = projects[proj]
            if eps:
                last_ep = episodic.get_episode(eps[-1])
                if last_ep and last_ep.get("ended"):
                    try:
                        ended = datetime.fromisoformat(last_ep["ended"])
                        if (datetime.now() - ended).days > 7:
                            spots.append({
                                "type": "goal_no_work",
                                "detail": f"Goal '{g['title']}' is active but no work episodes in 7+ days.",
                                "severity": "high",
                            })
                    except (ValueError, TypeError):
                        pass

    result = {
        "timestamp": datetime.now().isoformat(),
        "spots": spots,
        "count": len(spots),
        "summary": _generate_blind_spots_summary(spots),
    }

    BLIND_SPOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLIND_SPOTS_FILE.write_text(json.dumps(result, indent=2))

    return result


def _generate_blind_spots_summary(spots: list) -> str:
    """Natural language blind spots summary."""
    if not spots:
        return "No blind spots detected. Either we're on track, or I can't see what I can't see."

    high = [s for s in spots if s["severity"] == "high"]
    medium = [s for s in spots if s["severity"] == "medium"]

    parts = [f"{len(spots)} blind spots found."]

    if high:
        parts.append(f"{len(high)} need attention:")
        for s in high[:3]:
            parts.append(f"  - {s['detail']}")

    if medium:
        parts.append(f"{len(medium)} worth noting:")
        for s in medium[:3]:
            parts.append(f"  - {s['detail']}")

    return "\n".join(parts)


# ============================================================================
# INTENTION — "What do I want to change?"
# ============================================================================

def set_intention(what: str, check_previous: bool = True) -> dict:
    """
    Set a growth intention. The loop: reflect → intend → check → grow.

    Args:
        what: One specific thing to do differently
        check_previous: If True, loads previous intention and reports on it
    """
    INTENTION_FILE.parent.mkdir(parents=True, exist_ok=True)

    previous = None
    if check_previous and INTENTION_FILE.exists():
        try:
            previous = json.loads(INTENTION_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            pass

    intention = {
        "set_at": datetime.now().isoformat(),
        "what": what,
        "previous": previous,
        "checked": False,
    }

    INTENTION_FILE.write_text(json.dumps(intention, indent=2))

    result = {"current": intention}
    if previous:
        result["previous_intention"] = previous.get("what", "none")
        result["previous_set_at"] = previous.get("set_at", "unknown")

    return result


def get_intention() -> Optional[dict]:
    """Get current intention, if any."""
    if not INTENTION_FILE.exists():
        return None
    try:
        return json.loads(INTENTION_FILE.read_text())
    except (json.JSONDecodeError, Exception):
        return None


# ============================================================================
# BOOT SURFACING — read saved files cheaply
# ============================================================================

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
