"""
Elara Outcome Tracking — Link decisions to results. Close the learning loop.

Storage: ~/.claude/elara-outcomes/ (JSON files, one per outcome)

We make decisions but never check if they were right.
"Chose asyncio" → "debugging harder" → "lesson: only worth it above 100 connections"
That's calibrated intuition.
"""

import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from core.paths import get_paths
from daemon.schemas import Outcome, load_validated, save_validated, ElaraNotFoundError, ElaraValidationError

logger = logging.getLogger("elara.outcomes")

OUTCOMES_DIR = get_paths().outcomes_dir


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
    model = load_validated(path, Outcome)
    return model.model_dump()


def _save_outcome(outcome: Dict):
    _ensure_dirs()
    model = Outcome.model_validate(outcome)
    path = _outcome_path(outcome["outcome_id"])
    save_validated(path, model)


def _load_all_outcomes() -> List[Dict]:
    _ensure_dirs()
    outcomes = []
    for p in sorted(OUTCOMES_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                model = load_validated(p, Outcome)
                outcomes.append(model.model_dump())
            except Exception:
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
    logger.info("Recording outcome: %s", decision[:80])
    outcome_id = _generate_id(decision)
    outcome = Outcome(
        outcome_id=outcome_id,
        decision=decision,
        context=context,
        reasoning_trail=reasoning_trail,
        predicted=predicted,
        actual=None,
        assessment="too_early",
        lesson=None,
        tags=tags or [],
        recorded=datetime.now().isoformat(),
        checked=None,
    ).model_dump()
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
        raise ElaraNotFoundError(f"Outcome {outcome_id} not found.")

    logger.info("Checking outcome %s: assessment=%s", outcome_id, assessment)
    if assessment not in ("win", "partial_win", "loss", "too_early"):
        raise ElaraValidationError("assessment must be 'win', 'partial_win', 'loss', or 'too_early'.")

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
    logger.debug("Computing outcome stats")
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


# ============================================================================
# Pitch tracking (business partner layer)
# ============================================================================

def record_pitch(
    idea_id: str,
    channel: str,
    audience: str,
    framing: str,
    predicted: str,
    tags: Optional[List[str]] = None,
) -> Dict:
    """
    Record a pitch attempt as an outcome with business metadata.
    Convenience wrapper around record_outcome().
    """
    decision = f"Pitch {idea_id} on {channel}"
    context = f"Audience: {audience}, Framing: {framing}"

    outcome = record_outcome(
        decision=decision,
        context=context,
        predicted=predicted,
        tags=(tags or []) + [idea_id, "pitch", channel],
    )

    outcome["pitch_metadata"] = {
        "idea_id": idea_id,
        "channel": channel,
        "audience": audience,
        "framing": framing,
        "response_metric": None,
    }
    _save_outcome(outcome)
    return outcome


def get_pitch_stats(idea_id: str) -> Dict:
    """Win rate by channel and by framing for a specific idea's pitches."""
    outcomes = _load_all_outcomes()
    pitches = [
        o for o in outcomes
        if o.get("pitch_metadata", {}).get("idea_id") == idea_id
    ]

    if not pitches:
        return {"idea_id": idea_id, "total_pitches": 0, "by_channel": {}, "by_framing": {}}

    by_channel = {}
    by_framing = {}

    for p in pitches:
        meta = p["pitch_metadata"]
        assessment = p.get("assessment", "too_early")

        # Channel stats
        ch = meta.get("channel", "unknown")
        if ch not in by_channel:
            by_channel[ch] = {"total": 0, "wins": 0, "losses": 0}
        by_channel[ch]["total"] += 1
        if assessment == "win":
            by_channel[ch]["wins"] += 1
        elif assessment == "loss":
            by_channel[ch]["losses"] += 1

        # Framing stats
        fr = meta.get("framing", "unknown")
        if fr not in by_framing:
            by_framing[fr] = {"total": 0, "wins": 0, "losses": 0}
        by_framing[fr]["total"] += 1
        if assessment == "win":
            by_framing[fr]["wins"] += 1
        elif assessment == "loss":
            by_framing[fr]["losses"] += 1

    # Compute win rates
    for stats in list(by_channel.values()) + list(by_framing.values()):
        checked = stats["wins"] + stats["losses"]
        stats["win_rate"] = round(stats["wins"] / checked, 2) if checked > 0 else None

    return {
        "idea_id": idea_id,
        "total_pitches": len(pitches),
        "by_channel": by_channel,
        "by_framing": by_framing,
    }


def get_pitch_lessons(idea_id: str) -> List[Dict]:
    """Get lessons from checked pitches for this idea."""
    outcomes = _load_all_outcomes()
    pitches = [
        o for o in outcomes
        if o.get("pitch_metadata", {}).get("idea_id") == idea_id
        and o.get("lesson")
    ]

    return [
        {
            "channel": o["pitch_metadata"].get("channel"),
            "framing": o["pitch_metadata"].get("framing"),
            "assessment": o.get("assessment"),
            "lesson": o["lesson"],
        }
        for o in pitches
    ]


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
