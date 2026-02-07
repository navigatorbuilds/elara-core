"""
Elara Self-Awareness — Blind Spots lens.

"What am I missing?" — contrarian: stale goals, repeating mistakes, avoidance.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List

BLIND_SPOTS_FILE = Path.home() / ".claude" / "elara-blind-spots.json"


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
