"""
Elara Self-Awareness — Reflect lens.

"Who have I been?" — self-portrait from mood + behavior data.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List

from core.paths import get_paths

logger = logging.getLogger("elara.awareness.reflect")

REFLECTIONS_DIR = get_paths().reflections_dir


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
