"""
Elara Self-Awareness Engine

Five lenses, one growth loop:
- reflect()     — "Who have I been?" (self-portrait from mood + behavior data)
- pulse()       — "How are we doing?" (relationship health from session patterns)
- blind_spots() — "What am I missing?" (contrarian: stale goals, repeating mistakes, avoidance)
- intention()   — "What do I want to change?" (closes the loop: awareness → growth)
- proactive     — "What should I notice?" (pattern detection surfaced at boot / mid-session)

Runs on session end or on demand. Saves to files that boot reads cheaply.
Proactive observations are pure Python logic — zero token cost.
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

    Checks: stale goals, repeating corrections, abandoned projects,
    dormant corrections (never activated).
    """
    from daemon.goals import list_goals, stale_goals
    from daemon.corrections import list_corrections, get_dormant_corrections
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

    # --- Dormant corrections (never activated) ---
    dormant = get_dormant_corrections(days=14)
    for d in dormant:
        if d.get("times_surfaced", 0) == 0:
            dormant_days = (datetime.now() - datetime.fromisoformat(d["date"])).days
            if dormant_days >= 3:
                spots.append({
                    "type": "dormant_correction",
                    "detail": f"Correction #{d['id']} '{d['mistake'][:50]}' has never been activated ({dormant_days}d old). Still relevant?",
                    "severity": "medium" if dormant_days < 14 else "high",
                })

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

    # --- Recurring problem areas (from reasoning trails) ---
    try:
        from daemon.reasoning import get_recurring_problem_tags
        recurring = get_recurring_problem_tags(min_count=3)
        for r in recurring:
            spots.append({
                "type": "recurring_problem",
                "detail": f"Tag '{r['tag']}' appears in {r['count']} reasoning trails. Systemic issue?",
                "severity": "high" if r["count"] >= 5 else "medium",
            })
    except Exception:
        pass

    # --- Outcome loss patterns ---
    try:
        from daemon.outcomes import get_loss_patterns, get_unchecked_outcomes
        loss_patterns = get_loss_patterns(min_losses=2)
        for p in loss_patterns:
            spots.append({
                "type": "outcome_loss_pattern",
                "detail": f"Tag '{p['tag']}' has {p['loss_count']} losses. Overestimating this area?",
                "severity": "high" if p["loss_count"] >= 3 else "medium",
            })

        forgotten = get_unchecked_outcomes(days_old=7)
        if len(forgotten) >= 3:
            spots.append({
                "type": "forgotten_decisions",
                "detail": f"{len(forgotten)} decisions recorded but never checked (7+ days). Close the loop.",
                "severity": "medium",
            })
    except Exception:
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
# PROACTIVE PRESENCE — noticing things before being asked
# ============================================================================

# Session state — tracks what's been surfaced this session
PROACTIVE_SESSION_FILE = Path.home() / ".claude" / "elara-proactive-session.json"


def _load_proactive_session() -> dict:
    """Load proactive session state."""
    if PROACTIVE_SESSION_FILE.exists():
        try:
            return json.loads(PROACTIVE_SESSION_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "observations_surfaced": 0,
        "last_observation_time": None,
        "surfaced_types": [],
        "session_start": None,
        "cooldown_until": None,
    }


def _save_proactive_session(data: dict) -> None:
    """Save proactive session state."""
    PROACTIVE_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROACTIVE_SESSION_FILE.write_text(json.dumps(data, indent=2))


def _record_observation(obs_type: str) -> None:
    """Record that an observation was surfaced (for cooldown tracking)."""
    session = _load_proactive_session()
    session["observations_surfaced"] += 1
    session["last_observation_time"] = datetime.now().isoformat()
    session["surfaced_types"].append(obs_type)
    session["surfaced_types"] = session["surfaced_types"][-10:]
    _save_proactive_session(session)


def _can_observe() -> bool:
    """Check if we're allowed to surface another observation."""
    session = _load_proactive_session()

    # Max 3 observations per session
    if session["observations_surfaced"] >= 3:
        return False

    # Minimum 5 minutes between observations
    if session.get("last_observation_time"):
        try:
            last = datetime.fromisoformat(session["last_observation_time"])
            if (datetime.now() - last).total_seconds() < 300:
                return False
        except (ValueError, TypeError):
            pass

    return True


def reset_proactive_session() -> None:
    """Reset proactive session state (call at session start)."""
    data = {
        "observations_surfaced": 0,
        "last_observation_time": None,
        "surfaced_types": [],
        "session_start": datetime.now().isoformat(),
        "cooldown_until": None,
    }
    _save_proactive_session(data)


# --- Observation generators — each returns an observation dict or None ---

def _check_session_gap() -> Optional[Dict]:
    """Detect notable gaps between sessions."""
    try:
        from daemon.presence import get_stats
        stats = get_stats()
    except ImportError:
        return None

    absence_min = stats.get("absence_minutes")
    if absence_min is None:
        return None

    absence_hours = absence_min / 60

    if absence_hours > 48:
        days = int(absence_hours / 24)
        return {
            "type": "long_gap",
            "severity": "notable",
            "message": f"It's been {days} days. That's unusual for us.",
            "suggestion": "check_in",
        }

    return None


def _check_time_pattern() -> Optional[Dict]:
    """Detect unusual session timing."""
    hour = datetime.now().hour

    if 2 <= hour < 5:
        return {
            "type": "very_late",
            "severity": "gentle",
            "message": "It's past 2 AM. You should probably sleep.",
            "suggestion": "acknowledge_late",
        }

    return None


def _check_mood_trend() -> Optional[Dict]:
    """Detect mood trends across recent journal entries."""
    try:
        from daemon.state import read_mood_journal
        from daemon.emotions import get_primary_emotion
    except ImportError:
        return None

    journal = read_mood_journal(n=20)
    if len(journal) < 5:
        return None

    recent = journal[-10:]
    valences = [e.get("v", 0.5) for e in recent]
    energies = [e.get("e", 0.5) for e in recent]

    v_trend = _simple_trend(valences)

    avg_energy = sum(energies) / len(energies)
    if avg_energy < 0.3:
        current_emotion = get_primary_emotion(valences[-1], energies[-1], recent[-1].get("o", 0.5))
        return {
            "type": "low_energy",
            "severity": "gentle",
            "message": f"Energy's been low lately. Currently feeling {current_emotion}.",
            "suggestion": "lighter_work",
            "data": {"avg_energy": round(avg_energy, 2)},
        }

    if v_trend < -0.03:
        return {
            "type": "valence_declining",
            "severity": "notable",
            "message": "Mood's been drifting down across recent interactions.",
            "suggestion": "check_in",
            "data": {"trend": round(v_trend, 3)},
        }

    if v_trend > 0.04:
        return {
            "type": "valence_rising",
            "severity": "positive",
            "message": "Mood's been trending up. Good stretch.",
            "suggestion": "acknowledge",
            "data": {"trend": round(v_trend, 3)},
        }

    return None


def _check_session_pattern() -> Optional[Dict]:
    """Detect patterns in session history (all late nights, no drift, etc.)."""
    try:
        from memory.episodic import get_episodic
    except ImportError:
        return None

    episodic = get_episodic()
    recent = episodic.get_recent_episodes(n=10)

    if len(recent) < 3:
        return None

    types = [ep.get("type", "work") for ep in recent]
    work_count = types.count("work")
    drift_count = types.count("drift")

    if work_count >= 5 and drift_count == 0:
        return {
            "type": "all_work_no_drift",
            "severity": "gentle",
            "message": f"Last {len(recent)} sessions have been all work. No drift time.",
            "suggestion": "balance",
        }

    late_count = 0
    for ep in recent[:5]:
        started = ep.get("started", "")
        try:
            hour = datetime.fromisoformat(started).hour
            if hour >= 22 or hour < 6:
                late_count += 1
        except (ValueError, TypeError):
            pass

    if late_count >= 4:
        return {
            "type": "all_late_night",
            "severity": "gentle",
            "message": "You've been burning the midnight oil. A lot.",
            "suggestion": "sleep_pattern",
        }

    return None


def _check_milestone_streak() -> Optional[Dict]:
    """Detect milestone streaks — many things shipped recently."""
    try:
        from memory.episodic import get_episodic
    except ImportError:
        return None

    episodic = get_episodic()
    recent = episodic.get_recent_episodes(n=5)

    total_milestones = 0
    completions = 0
    for ep in recent:
        milestones = ep.get("milestones", [])
        total_milestones += len(milestones)
        completions += sum(1 for m in milestones if m.get("type") == "completion")

    if completions >= 3:
        return {
            "type": "shipping_streak",
            "severity": "positive",
            "message": f"We've shipped {completions} things in the last {len(recent)} sessions. Productive stretch.",
            "suggestion": "acknowledge",
        }

    return None


def _check_stale_goals() -> Optional[Dict]:
    """Check if goals are going stale."""
    try:
        from daemon.goals import stale_goals
    except ImportError:
        return None

    stale = stale_goals(days=7)
    if stale and len(stale) >= 2:
        names = [g["title"][:40] for g in stale[:3]]
        return {
            "type": "stale_goals",
            "severity": "notable",
            "message": f"{len(stale)} goals haven't been touched in a week: {', '.join(names)}",
            "suggestion": "review_goals",
        }

    return None


def _check_imprint_weight() -> Optional[Dict]:
    """Check if carrying heavy emotional imprints."""
    try:
        from daemon.state import get_imprints
    except ImportError:
        return None

    imprints = get_imprints(min_strength=0.6)
    if len(imprints) >= 3:
        feelings = [imp.get("feeling", "something")[:30] for imp in imprints[:3]]
        return {
            "type": "heavy_imprints",
            "severity": "gentle",
            "message": f"Carrying a lot emotionally right now: {'; '.join(feelings)}",
            "suggestion": "acknowledge",
        }

    return None


# --- Proactive API ---

def get_boot_observations() -> List[Dict]:
    """
    Run all checks at session start. Returns observations worth surfacing.
    Resets session counter.
    """
    reset_proactive_session()

    observations = []
    checkers = [
        _check_session_gap,
        _check_time_pattern,
        _check_mood_trend,
        _check_session_pattern,
        _check_stale_goals,
        _check_imprint_weight,
    ]

    for checker in checkers:
        try:
            obs = checker()
            if obs:
                observations.append(obs)
        except Exception:
            pass  # Never crash on observation generation

    return observations


def get_mid_session_observations() -> List[Dict]:
    """
    Check for observations during a session. Respects cooldown.
    Call this periodically or at natural breaks.
    """
    if not _can_observe():
        return []

    observations = []
    session = _load_proactive_session()
    already_surfaced = set(session.get("surfaced_types", []))

    checkers = [
        _check_mood_trend,
        _check_milestone_streak,
        _check_imprint_weight,
    ]

    for checker in checkers:
        try:
            obs = checker()
            if obs and obs["type"] not in already_surfaced:
                observations.append(obs)
        except Exception:
            pass

    return observations


def surface_observation(observation: Dict) -> str:
    """
    Mark an observation as surfaced and return the message.
    This is what I actually say to the user.
    """
    _record_observation(observation["type"])
    return observation["message"]


def get_observation_count() -> int:
    """How many observations have been surfaced this session?"""
    session = _load_proactive_session()
    return session.get("observations_surfaced", 0)


# ============================================================================
# HELPERS
# ============================================================================

def _simple_trend(values: list) -> float:
    """
    Calculate simple linear trend.
    Returns slope: positive = rising, negative = falling.
    """
    n = len(values)
    if n < 2:
        return 0

    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0

    return numerator / denominator


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
