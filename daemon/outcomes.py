"""
Elara Outcome Tracking — Link decisions to results. Close the learning loop.

Storage: ~/.claude/elara-outcomes/ (JSON files, one per outcome)

We make decisions but never check if they were right.
"Chose asyncio" → "debugging harder" → "lesson: only worth it above 100 connections"
That's calibrated intuition.
"""

import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

OUTCOMES_DIR = Path.home() / ".claude" / "elara-outcomes"


# ============================================================================
# Storage layer
# ============================================================================

def _ensure_dirs():
    OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)


def _outcome_path(outcome_id: str) -> Path:
    return OUTCOMES_DIR / f"{outcome_id}.json"


def _generate_id(decision: str) -> str:
    raw = f"{decision}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_outcome(outcome_id: str) -> Optional[Dict]:
    path = _outcome_path(outcome_id)
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def _save_outcome(outcome: Dict):
    _ensure_dirs()
    path = _outcome_path(outcome["outcome_id"])
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(outcome, f, indent=2)
    os.rename(str(tmp), str(path))


def _load_all_outcomes() -> List[Dict]:
    _ensure_dirs()
    outcomes = []
    for p in sorted(OUTCOMES_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                with open(p) as f:
                    outcomes.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return outcomes


# ============================================================================
# Core operations
# ============================================================================

def record_outcome(
    decision: str,
    context: str,
    predicted: str,
    tags: Optional[List[str]] = None,
    reasoning_trail: Optional[str] = None,
) -> Dict:
    """
    Record a decision and what we expected to happen.
    Assessment and lesson come later via check_outcome().
    """
    outcome_id = _generate_id(decision)
    outcome = {
        "outcome_id": outcome_id,
        "decision": decision,
        "context": context,
        "reasoning_trail": reasoning_trail,
        "predicted": predicted,
        "actual": None,
        "assessment": "too_early",
        "lesson": None,
        "tags": tags or [],
        "recorded": datetime.now().isoformat(),
        "checked": None,
    }
    _save_outcome(outcome)
    return outcome


def check_outcome(
    outcome_id: str,
    actual: str,
    assessment: str,
    lesson: Optional[str] = None,
) -> Dict:
    """
    Check a decision against reality. Close the loop.

    assessment: "win", "partial_win", "loss", "too_early"
    """
    outcome = _load_outcome(outcome_id)
    if not outcome:
        return {"error": f"Outcome {outcome_id} not found."}

    if assessment not in ("win", "partial_win", "loss", "too_early"):
        return {"error": "assessment must be 'win', 'partial_win', 'loss', or 'too_early'."}

    outcome["actual"] = actual
    outcome["assessment"] = assessment
    outcome["lesson"] = lesson
    outcome["checked"] = datetime.now().isoformat()

    _save_outcome(outcome)
    return outcome


def get_outcome(outcome_id: str) -> Optional[Dict]:
    """Get a single outcome by ID."""
    return _load_outcome(outcome_id)


def list_outcomes(
    assessment: Optional[str] = None,
    tag: Optional[str] = None,
    unchecked_only: bool = False,
    n: int = 20,
) -> List[Dict]:
    """List outcomes, optionally filtered."""
    outcomes = _load_all_outcomes()

    if assessment:
        outcomes = [o for o in outcomes if o.get("assessment") == assessment]
    if tag:
        outcomes = [o for o in outcomes if tag in o.get("tags", [])]
    if unchecked_only:
        outcomes = [o for o in outcomes if o.get("assessment") == "too_early"]

    # Most recent first
    outcomes.sort(key=lambda o: o.get("recorded", ""), reverse=True)
    return outcomes[:n]


def search_outcomes_by_tags(tags: List[str], n: int = 10) -> List[Dict]:
    """Find past outcomes with overlapping tags — check before similar decisions."""
    outcomes = _load_all_outcomes()
    tag_set = set(tags)
    scored = []
    for o in outcomes:
        overlap = len(tag_set & set(o.get("tags", [])))
        if overlap > 0:
            scored.append((overlap, o))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [o for _, o in scored[:n]]


# ============================================================================
# Analytics (for blind_spots and dreams integration)
# ============================================================================

def get_outcome_stats() -> Dict:
    """Overall stats: win rate, common loss tags, unchecked count."""
    outcomes = _load_all_outcomes()
    if not outcomes:
        return {
            "total": 0,
            "checked": 0,
            "unchecked": 0,
            "wins": 0,
            "partial_wins": 0,
            "losses": 0,
            "win_rate": None,
        }

    checked = [o for o in outcomes if o.get("assessment") != "too_early"]
    unchecked = [o for o in outcomes if o.get("assessment") == "too_early"]
    wins = [o for o in checked if o.get("assessment") == "win"]
    partials = [o for o in checked if o.get("assessment") == "partial_win"]
    losses = [o for o in checked if o.get("assessment") == "loss"]

    win_rate = None
    if checked:
        # Count wins as 1, partial_wins as 0.5
        score = len(wins) + 0.5 * len(partials)
        win_rate = round(score / len(checked), 2)

    return {
        "total": len(outcomes),
        "checked": len(checked),
        "unchecked": len(unchecked),
        "wins": len(wins),
        "partial_wins": len(partials),
        "losses": len(losses),
        "win_rate": win_rate,
    }


def get_loss_patterns(min_losses: int = 2) -> List[Dict]:
    """
    Find tags that appear in multiple losses — overestimation patterns.
    Used by blind_spots(): "You tend to overestimate X."
    """
    outcomes = _load_all_outcomes()
    losses = [o for o in outcomes if o.get("assessment") == "loss"]

    tag_counts = {}
    tag_lessons = {}
    for o in losses:
        for tag in o.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if tag not in tag_lessons:
                tag_lessons[tag] = []
            if o.get("lesson"):
                tag_lessons[tag].append(o["lesson"])

    patterns = []
    for tag, count in tag_counts.items():
        if count >= min_losses:
            patterns.append({
                "tag": tag,
                "loss_count": count,
                "lessons": tag_lessons.get(tag, []),
            })

    patterns.sort(key=lambda x: x["loss_count"], reverse=True)
    return patterns


def get_unchecked_outcomes(days_old: int = 7) -> List[Dict]:
    """Get outcomes that were recorded but never checked — forgotten decisions."""
    outcomes = _load_all_outcomes()
    now = datetime.now()
    old_unchecked = []

    for o in outcomes:
        if o.get("assessment") != "too_early":
            continue
        try:
            recorded = datetime.fromisoformat(o["recorded"])
            age_days = (now - recorded).days
            if age_days >= days_old:
                o["_age_days"] = age_days
                old_unchecked.append(o)
        except (ValueError, TypeError):
            pass

    old_unchecked.sort(key=lambda o: o.get("_age_days", 0), reverse=True)
    return old_unchecked
