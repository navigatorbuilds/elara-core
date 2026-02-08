# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Business Intelligence — Track ideas, competitors, viability scoring.

Wraps reasoning + synthesis + outcomes with business vocabulary.
No ChromaDB needed (small dataset, direct JSON lookup).

Storage: ~/.claude/elara-business/ (one JSON per idea)
"""

import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from core.paths import get_paths
from daemon.events import bus, Events
from daemon.schemas import (
    BusinessIdea, Competitor, IdeaScore, load_validated, save_validated,
    ElaraNotFoundError, ElaraValidationError,
)

logger = logging.getLogger("elara.business")

BUSINESS_DIR = get_paths().business_dir

# Status lifecycle
VALID_STATUSES = ("exploring", "validated", "building", "launched", "abandoned")


# ============================================================================
# Storage layer
# ============================================================================

def _ensure_dirs():
    BUSINESS_DIR.mkdir(parents=True, exist_ok=True)


def _idea_path(idea_id: str) -> Path:
    return BUSINESS_DIR / f"{idea_id}.json"


def _generate_id(name: str) -> str:
    """Slug-style ID from name."""
    slug = name.lower().strip()
    slug = slug.replace(" ", "-").replace("_", "-")
    # Keep only alphanumeric + hyphens
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    # Collapse multiple hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:40] or hashlib.sha256(name.encode()).hexdigest()[:12]


def _load_idea(idea_id: str) -> Optional[Dict]:
    path = _idea_path(idea_id)
    if not path.exists():
        return None
    try:
        model = load_validated(path, BusinessIdea)
        return model.model_dump()
    except Exception as e:
        logger.warning("Failed to load idea %s: %s", idea_id, e)
        return None


def _save_idea(idea: Dict):
    _ensure_dirs()
    model = BusinessIdea.model_validate(idea)
    path = _idea_path(idea["idea_id"])
    save_validated(path, model)


def _load_all_ideas() -> List[Dict]:
    _ensure_dirs()
    ideas = []
    for p in sorted(BUSINESS_DIR.glob("*.json")):
        if not p.name.endswith(".tmp"):
            try:
                model = load_validated(p, BusinessIdea)
                ideas.append(model.model_dump())
            except Exception as e:
                logger.warning("Failed to load idea file %s: %s", p.name, e)
    return ideas


# ============================================================================
# Core operations
# ============================================================================

def create_idea(
    name: str,
    description: str,
    target_audience: str = "",
    your_angle: str = "",
    tags: Optional[List[str]] = None,
) -> Dict:
    """Create a new business idea."""
    logger.info("Creating business idea: %s", name)
    idea_id = _generate_id(name)

    # Don't overwrite existing
    if _load_idea(idea_id):
        raise ElaraValidationError(f"Idea '{idea_id}' already exists. Use update_idea() to modify.")

    now = datetime.now().isoformat()
    idea = BusinessIdea(
        idea_id=idea_id,
        name=name,
        description=description,
        target_audience=target_audience,
        your_angle=your_angle,
        tags=tags or [],
        created=now,
        last_touched=now,
    ).model_dump()
    _save_idea(idea)
    bus.emit(Events.IDEA_CREATED, {"idea_id": idea_id, "name": name}, source="business")
    return idea


def add_competitor(
    idea_id: str,
    name: str,
    strengths: str = "",
    weaknesses: str = "",
    url: str = "",
) -> Dict:
    """Add a competitor to an idea."""
    idea = _load_idea(idea_id)
    if not idea:
        raise ElaraNotFoundError(f"Idea '{idea_id}' not found.")

    logger.debug("Adding competitor '%s' to idea %s", name, idea_id)
    competitor = Competitor(
        name=name,
        strengths=strengths,
        weaknesses=weaknesses,
        url=url,
        added=datetime.now().isoformat(),
    ).model_dump()
    idea["competitors"].append(competitor)
    idea["last_touched"] = datetime.now().isoformat()
    _save_idea(idea)
    return idea


def score_idea(
    idea_id: str,
    problem: int,
    market: int,
    effort: int,
    monetization: int,
    fit: int,
) -> Dict:
    """Score an idea on 5 axes (each 1-5). Total /25."""
    idea = _load_idea(idea_id)
    if not idea:
        raise ElaraNotFoundError(f"Idea '{idea_id}' not found.")

    # Clamp to 1-5
    axes = {"problem": problem, "market": market, "effort": effort,
            "monetization": monetization, "fit": fit}
    for k, v in axes.items():
        axes[k] = max(1, min(5, v))

    total = sum(axes.values())
    logger.info("Scoring idea %s: %d/25", idea_id, total)
    score = IdeaScore(
        **axes,
        total=total,
        scored_at=datetime.now().isoformat(),
    ).model_dump()
    idea["score"] = score
    idea["last_touched"] = datetime.now().isoformat()
    _save_idea(idea)
    bus.emit(Events.IDEA_SCORED, {"idea_id": idea_id, "total": total}, source="business")
    return idea


def update_idea(
    idea_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict:
    """Update idea status or add a note."""
    idea = _load_idea(idea_id)
    if not idea:
        raise ElaraNotFoundError(f"Idea '{idea_id}' not found.")

    if status:
        if status not in VALID_STATUSES:
            raise ElaraValidationError(f"Invalid status '{status}'. Use: {', '.join(VALID_STATUSES)}")
        idea["status"] = status

    if notes:
        idea["notes"].append({
            "text": notes,
            "added": datetime.now().isoformat(),
        })

    idea["last_touched"] = datetime.now().isoformat()
    _save_idea(idea)
    return idea


def get_idea(idea_id: str) -> Optional[Dict]:
    """Get full idea with all data."""
    return _load_idea(idea_id)


def list_ideas(
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    n: int = 20,
) -> List[Dict]:
    """List ideas, optionally filtered by status and minimum score."""
    ideas = _load_all_ideas()

    if status:
        ideas = [i for i in ideas if i.get("status") == status]

    if min_score is not None:
        ideas = [
            i for i in ideas
            if i.get("score") and i["score"].get("total", 0) >= min_score
        ]

    # Sort by last_touched descending
    ideas.sort(key=lambda i: i.get("last_touched", ""), reverse=True)
    return ideas[:n]


def link_to_reasoning(idea_id: str, trail_id: str) -> Dict:
    """Connect an idea to a reasoning trail."""
    idea = _load_idea(idea_id)
    if not idea:
        raise ElaraNotFoundError(f"Idea '{idea_id}' not found.")

    if trail_id not in idea["reasoning_trails"]:
        idea["reasoning_trails"].append(trail_id)
        idea["last_touched"] = datetime.now().isoformat()
        _save_idea(idea)
    return idea


def link_to_outcome(idea_id: str, outcome_id: str) -> Dict:
    """Connect an idea to a decision outcome."""
    idea = _load_idea(idea_id)
    if not idea:
        raise ElaraNotFoundError(f"Idea '{idea_id}' not found.")

    if outcome_id not in idea["outcomes"]:
        idea["outcomes"].append(outcome_id)
        idea["last_touched"] = datetime.now().isoformat()
        _save_idea(idea)
    return idea


# ============================================================================
# Analytics & Boot
# ============================================================================

def get_stale_ideas(days: int = 14) -> List[Dict]:
    """Ideas not touched in N days that aren't abandoned/launched."""
    ideas = _load_all_ideas()
    now = datetime.now()
    stale = []

    for idea in ideas:
        if idea.get("status") in ("abandoned", "launched"):
            continue
        try:
            last = datetime.fromisoformat(idea.get("last_touched", ""))
            age = (now - last).days
            if age >= days:
                idea["_stale_days"] = age
                stale.append(idea)
        except (ValueError, TypeError):
            pass

    stale.sort(key=lambda i: i.get("_stale_days", 0), reverse=True)
    return stale


def get_idea_stats() -> Dict:
    """Overall business idea stats."""
    ideas = _load_all_ideas()
    if not ideas:
        return {"total": 0, "by_status": {}, "scored": 0, "avg_score": None}

    by_status = {}
    scored = [i for i in ideas if i.get("score")]
    for i in ideas:
        s = i.get("status", "exploring")
        by_status[s] = by_status.get(s, 0) + 1

    avg_score = None
    if scored:
        avg_score = round(
            sum(i["score"]["total"] for i in scored) / len(scored), 1
        )

    return {
        "total": len(ideas),
        "by_status": by_status,
        "scored": len(scored),
        "avg_score": avg_score,
    }


def boot_summary() -> Optional[str]:
    """
    Boot-time business summary. Returns formatted text or None.
    Shows: active ideas, approaching deadlines, stale ideas.
    """
    ideas = _load_all_ideas()
    if not ideas:
        return None

    active = [i for i in ideas if i.get("status") in ("exploring", "validated", "building")]
    stale = get_stale_ideas(days=14)

    if not active and not stale:
        return None

    lines = []

    # Active ideas by status
    building = [i for i in active if i["status"] == "building"]
    validated = [i for i in active if i["status"] == "validated"]
    exploring = [i for i in active if i["status"] == "exploring"]

    if building:
        for i in building:
            score_str = f" ({i['score']['total']}/25)" if i.get("score") else ""
            lines.append(f"[Business] 🔨 Building: {i['name']}{score_str}")

    if validated:
        for i in validated:
            score_str = f" ({i['score']['total']}/25)" if i.get("score") else ""
            lines.append(f"[Business] ✓ Validated: {i['name']}{score_str}")

    if exploring and len(lines) < 3:
        for i in exploring[:2]:
            score_str = f" ({i['score']['total']}/25)" if i.get("score") else ""
            lines.append(f"[Business] ? Exploring: {i['name']}{score_str}")

    # Stale warning
    if stale:
        names = ", ".join(i["name"] for i in stale[:3])
        lines.append(f"[Business] ⚠ Stale ({len(stale)}): {names}")

    return "\n".join(lines) if lines else None


def generate_review(idea_id: str) -> Optional[str]:
    """Generate a full review report for an idea."""
    idea = _load_idea(idea_id)
    if not idea:
        return None

    lines = [
        f"# {idea['name']}",
        f"Status: {idea['status']} | Created: {idea['created'][:10]}",
        f"Last touched: {idea['last_touched'][:10]}",
        "",
        f"**Description:** {idea['description']}",
    ]

    if idea.get("target_audience"):
        lines.append(f"**Target:** {idea['target_audience']}")
    if idea.get("your_angle"):
        lines.append(f"**Angle:** {idea['your_angle']}")

    # Score
    if idea.get("score"):
        s = idea["score"]
        lines.append("")
        lines.append(f"**Score: {s['total']}/25**")
        lines.append(f"  Problem: {s['problem']}/5 | Market: {s['market']}/5 | Effort: {s['effort']}/5")
        lines.append(f"  Monetization: {s['monetization']}/5 | Fit: {s['fit']}/5")

    # Competitors
    if idea.get("competitors"):
        lines.append("")
        lines.append(f"**Competitors ({len(idea['competitors'])}):**")
        for c in idea["competitors"]:
            lines.append(f"  • {c['name']}")
            if c.get("strengths"):
                lines.append(f"    +: {c['strengths']}")
            if c.get("weaknesses"):
                lines.append(f"    -: {c['weaknesses']}")
            if c.get("url"):
                lines.append(f"    url: {c['url']}")

    # Linked reasoning trails
    if idea.get("reasoning_trails"):
        lines.append("")
        lines.append(f"**Reasoning trails:** {', '.join(idea['reasoning_trails'])}")

    # Linked outcomes
    if idea.get("outcomes"):
        lines.append("")
        lines.append(f"**Outcomes:** {', '.join(idea['outcomes'])}")

    # Notes
    if idea.get("notes"):
        lines.append("")
        lines.append("**Notes:**")
        for note in idea["notes"]:
            lines.append(f"  [{note.get('added', '?')[:10]}] {note['text']}")

    # Tags
    if idea.get("tags"):
        lines.append("")
        lines.append(f"**Tags:** {', '.join(idea['tags'])}")

    return "\n".join(lines)
