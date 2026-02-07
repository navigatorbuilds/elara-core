"""
Elara Reasoning Trails — Track hypothesis → evidence → conclusion → outcome chains.

Storage: ~/.claude/elara-reasoning/ (JSON files, one per trail)
Index:   ~/.claude/elara-reasoning-db/ (ChromaDB, cosine similarity)

When we debug something complex, track the chain:
  tried X → failed because Y → tried Z → worked because W

Next time a similar problem shows up, search trails before wasting an hour
re-discovering the same thing.
"""

import logging
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from daemon.schemas import (
    ReasoningTrail, Hypothesis, load_validated, save_validated,
    ElaraNotFoundError, ElaraValidationError,
)

logger = logging.getLogger("elara.reasoning")

REASONING_DIR = Path.home() / ".claude" / "elara-reasoning"
REASONING_DB_DIR = Path.home() / ".claude" / "elara-reasoning-db"


# ============================================================================
# Storage layer (JSON files — source of truth)
# ============================================================================

def _ensure_dirs():
    REASONING_DIR.mkdir(parents=True, exist_ok=True)


def _trail_path(trail_id: str) -> Path:
    return REASONING_DIR / f"{trail_id}.json"


def _generate_id(context: str) -> str:
    raw = f"{context}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_trail(trail_id: str) -> Optional[Dict]:
    path = _trail_path(trail_id)
    if not path.exists():
        return None
    model = load_validated(path, ReasoningTrail)
    return model.model_dump()


def _save_trail(trail: Dict):
    _ensure_dirs()
    model = ReasoningTrail.model_validate(trail)
    path = _trail_path(trail["trail_id"])
    save_validated(path, model)


def _load_all_trails() -> List[Dict]:
    _ensure_dirs()
    trails = []
    for p in sorted(REASONING_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                model = load_validated(p, ReasoningTrail)
                trails.append(model.model_dump())
            except Exception:
                pass
    return trails


# ============================================================================
# ChromaDB index (semantic search over trails)
# ============================================================================

def _get_collection():
    if not CHROMA_AVAILABLE:
        return None
    try:
        client = chromadb.PersistentClient(
            path=str(REASONING_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        return client.get_or_create_collection(
            name="elara_reasoning",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return None


def _index_trail(trail: Dict):
    collection = _get_collection()
    if not collection:
        return

    # Build searchable text from all parts of the trail
    parts = [trail.get("context", "")]
    for h in trail.get("hypotheses", []):
        parts.append(h.get("h", ""))
        parts.extend(h.get("evidence", []))
    parts.extend(trail.get("abandoned_approaches", []))
    if trail.get("final_solution"):
        parts.append(trail["final_solution"])
    if trail.get("breakthrough_trigger"):
        parts.append(trail["breakthrough_trigger"])

    text = " ".join(p for p in parts if p)
    if not text.strip():
        return

    metadata = {
        "started": trail.get("started", ""),
        "resolved": str(trail.get("resolved", False)),
        "tags": ",".join(trail.get("tags", [])),
    }

    try:
        collection.upsert(
            ids=[trail["trail_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception:
        pass


def _remove_from_index(trail_id: str):
    collection = _get_collection()
    if not collection:
        return
    try:
        collection.delete(ids=[trail_id])
    except Exception:
        pass


# ============================================================================
# Core operations
# ============================================================================

def start_trail(context: str, tags: Optional[List[str]] = None) -> Dict:
    """Start a new reasoning trail for a problem we're investigating."""
    logger.info("Starting reasoning trail: %s", context[:80])
    trail_id = _generate_id(context)
    trail = ReasoningTrail(
        trail_id=trail_id,
        started=datetime.now().isoformat(),
        context=context,
        tags=tags or [],
    ).model_dump()
    _save_trail(trail)
    _index_trail(trail)
    return trail


def add_hypothesis(
    trail_id: str,
    hypothesis: str,
    evidence: Optional[List[str]] = None,
    confidence: float = 0.5,
) -> Dict:
    """Add a hypothesis to an existing trail."""
    trail = _load_trail(trail_id)
    if not trail:
        raise ElaraNotFoundError(f"Trail {trail_id} not found.")

    logger.debug("Adding hypothesis to trail %s: %s", trail_id, hypothesis[:60])
    h = Hypothesis(
        h=hypothesis,
        evidence=evidence or [],
        confidence=round(confidence, 2),
        outcome=None,
        added=datetime.now().isoformat(),
    ).model_dump()
    trail["hypotheses"].append(h)
    _save_trail(trail)
    _index_trail(trail)
    return trail


def update_hypothesis(
    trail_id: str,
    hypothesis_index: int,
    outcome: Optional[str] = None,
    evidence: Optional[List[str]] = None,
    confidence: Optional[float] = None,
) -> Dict:
    """Update a hypothesis outcome or add evidence."""
    trail = _load_trail(trail_id)
    if not trail:
        raise ElaraNotFoundError(f"Trail {trail_id} not found.")

    hypotheses = trail.get("hypotheses", [])
    if hypothesis_index < 0 or hypothesis_index >= len(hypotheses):
        raise ElaraValidationError(f"Hypothesis index {hypothesis_index} out of range (0-{len(hypotheses)-1}).")

    h = hypotheses[hypothesis_index]
    if outcome:
        if outcome not in ("true", "false", "partial"):
            raise ElaraValidationError("outcome must be 'true', 'false', or 'partial'.")
        h["outcome"] = outcome
    if evidence:
        h["evidence"].extend(evidence)
    if confidence is not None:
        h["confidence"] = round(confidence, 2)

    _save_trail(trail)
    _index_trail(trail)
    return trail


def abandon_approach(trail_id: str, approach: str) -> Dict:
    """Record an approach we tried and dropped."""
    trail = _load_trail(trail_id)
    if not trail:
        raise ElaraNotFoundError(f"Trail {trail_id} not found.")

    trail["abandoned_approaches"].append(approach)
    _save_trail(trail)
    _index_trail(trail)
    return trail


def solve_trail(
    trail_id: str,
    solution: str,
    breakthrough_trigger: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict:
    """Mark a trail as solved."""
    trail = _load_trail(trail_id)
    if not trail:
        raise ElaraNotFoundError(f"Trail {trail_id} not found.")

    logger.info("Solving trail %s: %s", trail_id, solution[:80])
    trail["final_solution"] = solution
    trail["resolved"] = True
    trail["resolved_at"] = datetime.now().isoformat()
    if breakthrough_trigger:
        trail["breakthrough_trigger"] = breakthrough_trigger
    if tags:
        trail["tags"] = list(set(trail.get("tags", []) + tags))

    _save_trail(trail)
    _index_trail(trail)
    return trail


def search_trails(query: str, n: int = 5) -> List[Dict]:
    """Search past reasoning trails by problem similarity."""
    collection = _get_collection()
    if not collection:
        # Fallback: keyword search
        logger.warning("ChromaDB not available for reasoning, falling back to keyword search")
        return _keyword_search(query, n)

    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n, count),
        )

        trails = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, trail_id in enumerate(ids):
            trail = _load_trail(trail_id)
            if trail:
                # Cosine distance → similarity (0-1, higher = more similar)
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                trail["_similarity"] = round(similarity, 3)
                trails.append(trail)

        return trails
    except Exception:
        return _keyword_search(query, n)


def _keyword_search(query: str, n: int) -> List[Dict]:
    """Simple keyword fallback when ChromaDB isn't available."""
    query_words = set(query.lower().split())
    trails = _load_all_trails()
    scored = []
    for t in trails:
        text = f"{t.get('context','')} {t.get('final_solution','')} {' '.join(t.get('tags',[]))}".lower()
        overlap = len(query_words & set(text.split()))
        if overlap > 0:
            scored.append((overlap, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:n]]


def get_trail(trail_id: str) -> Optional[Dict]:
    """Get a single trail by ID."""
    return _load_trail(trail_id)


def list_trails(
    resolved: Optional[bool] = None,
    tag: Optional[str] = None,
    n: int = 20,
) -> List[Dict]:
    """List trails, optionally filtered."""
    trails = _load_all_trails()

    if resolved is not None:
        trails = [t for t in trails if t.get("resolved") == resolved]
    if tag:
        trails = [t for t in trails if tag in t.get("tags", [])]

    # Sort by most recent first
    trails.sort(key=lambda t: t.get("started", ""), reverse=True)
    return trails[:n]


def get_active_trail() -> Optional[Dict]:
    """Get the most recent unresolved trail (if any)."""
    unresolved = list_trails(resolved=False, n=1)
    return unresolved[0] if unresolved else None


# ============================================================================
# Analytics (for blind_spots integration)
# ============================================================================

def get_recurring_problem_tags(min_count: int = 3) -> List[Dict]:
    """
    Find tags that appear in multiple trails — recurring problem areas.
    Used by blind_spots() to surface patterns.
    """
    trails = _load_all_trails()
    tag_counts = {}
    tag_trails = {}

    for t in trails:
        for tag in t.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if tag not in tag_trails:
                tag_trails[tag] = []
            tag_trails[tag].append(t["trail_id"])

    recurring = []
    for tag, count in tag_counts.items():
        if count >= min_count:
            recurring.append({
                "tag": tag,
                "count": count,
                "trail_ids": tag_trails[tag],
            })

    recurring.sort(key=lambda x: x["count"], reverse=True)
    return recurring


def get_abandonment_rate() -> Dict:
    """Stats on how often we abandon approaches."""
    trails = _load_all_trails()
    if not trails:
        return {"total": 0, "abandoned_total": 0, "avg_per_trail": 0.0}

    total_abandoned = sum(len(t.get("abandoned_approaches", [])) for t in trails)
    return {
        "total_trails": len(trails),
        "abandoned_total": total_abandoned,
        "avg_per_trail": round(total_abandoned / len(trails), 1) if trails else 0.0,
        "unresolved": len([t for t in trails if not t.get("resolved")]),
    }


def reindex_all():
    """Rebuild ChromaDB index from JSON files. Run at boot if needed."""
    trails = _load_all_trails()
    for t in trails:
        _index_trail(t)
    return len(trails)
