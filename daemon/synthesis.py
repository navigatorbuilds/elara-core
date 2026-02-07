"""
Elara Idea Synthesis — Detect recurring half-formed ideas across sessions.

Storage: ~/.claude/elara-synthesis/ (JSON files, one per synthesis)
Index:   ~/.claude/elara-synthesis-db/ (ChromaDB, cosine similarity for seed clustering)

When the same idea keeps surfacing across sessions — even in different words —
this system notices and says: "You keep coming back to this. Ready to build?"
"""

import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from core.paths import get_paths
from daemon.schemas import Synthesis, SynthesisSeed, load_validated, save_validated, ElaraNotFoundError, ElaraValidationError

logger = logging.getLogger("elara.synthesis")

_p = get_paths()
SYNTHESIS_DIR = _p.synthesis_dir
SYNTHESIS_DB_DIR = _p.synthesis_db

# Clustering threshold — how similar two quotes need to be to count as same idea
SEED_SIMILARITY_THRESHOLD = 0.75


# ============================================================================
# Storage layer
# ============================================================================

def _ensure_dirs():
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)


def _synthesis_path(synthesis_id: str) -> Path:
    return SYNTHESIS_DIR / f"{synthesis_id}.json"


def _generate_id(concept: str) -> str:
    raw = f"{concept}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_synthesis(synthesis_id: str) -> Optional[Dict]:
    path = _synthesis_path(synthesis_id)
    if not path.exists():
        return None
    model = load_validated(path, Synthesis)
    return model.model_dump()


def _save_synthesis(synth: Dict):
    _ensure_dirs()
    model = Synthesis.model_validate(synth)
    path = _synthesis_path(synth["synthesis_id"])
    save_validated(path, model)


def _load_all_syntheses() -> List[Dict]:
    _ensure_dirs()
    syntheses = []
    for p in sorted(SYNTHESIS_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                model = load_validated(p, Synthesis)
                syntheses.append(model.model_dump())
            except Exception:
                pass
    return syntheses


# ============================================================================
# ChromaDB index (for seed clustering)
# ============================================================================

_chroma_client = None
_chroma_collection = None
_chroma_seed_collection = None


def _get_client():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    SYNTHESIS_DB_DIR.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(SYNTHESIS_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    return _chroma_client


def _get_collection():
    global _chroma_collection

    if not CHROMA_AVAILABLE:
        return None

    if _chroma_collection is not None:
        return _chroma_collection

    try:
        client = _get_client()
        _chroma_collection = client.get_or_create_collection(
            name="elara_synthesis",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to get synthesis ChromaDB collection: %s", e)
        return None


def _get_seed_collection():
    """Separate collection for individual seeds — used for clustering."""
    global _chroma_seed_collection

    if not CHROMA_AVAILABLE:
        return None

    if _chroma_seed_collection is not None:
        return _chroma_seed_collection

    try:
        client = _get_client()
        _chroma_seed_collection = client.get_or_create_collection(
            name="elara_synthesis_seeds",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_seed_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to get synthesis seed collection: %s", e)
        return None


def _index_synthesis(synth: Dict):
    """Index synthesis concept for searching."""
    collection = _get_collection()
    if not collection:
        return

    text = synth.get("concept", "")
    seeds = synth.get("seeds", [])
    if seeds:
        text += " " + " ".join(s.get("quote", "") for s in seeds)

    if not text.strip():
        return

    metadata = {
        "status": synth.get("status", "dormant"),
        "times_surfaced": str(synth.get("times_surfaced", 0)),
        "first_seen": synth.get("first_seen", ""),
    }

    try:
        collection.upsert(
            ids=[synth["synthesis_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception:
        pass


# ============================================================================
# Core operations
# ============================================================================

def create_synthesis(
    concept: str,
    seed_quote: str,
    seed_source: str = "conversation",
    seed_source_id: Optional[str] = None,
) -> Dict:
    """Manually create a synthesis from a recurring idea we've noticed."""
    logger.info("Creating synthesis: %s", concept)
    synthesis_id = _generate_id(concept)
    now = datetime.now().isoformat()

    seed = SynthesisSeed(
        source=seed_source,
        quote=seed_quote,
        date=now,
    ).model_dump()
    # Add source_id as extra field
    seed["source_id"] = seed_source_id

    synth = Synthesis(
        synthesis_id=synthesis_id,
        concept=concept,
        seeds=[seed],
        times_surfaced=1,
        first_seen=now,
        last_reinforced=now,
        status="dormant",
        confidence=0.3,
    ).model_dump()

    _save_synthesis(synth)
    _index_synthesis(synth)
    return synth


def add_seed(
    synthesis_id: str,
    quote: str,
    source: str = "conversation",
    source_id: Optional[str] = None,
) -> Dict:
    """Add a new seed to an existing synthesis — reinforces the idea."""
    synth = _load_synthesis(synthesis_id)
    if not synth:
        raise ElaraNotFoundError(f"Synthesis {synthesis_id} not found.")

    logger.debug("Adding seed to synthesis %s (now %d seeds)", synthesis_id, len(synth.get("seeds", [])) + 1)
    now = datetime.now().isoformat()
    seed = SynthesisSeed(
        source=source,
        quote=quote,
        date=now,
    ).model_dump()
    seed["source_id"] = source_id

    synth["seeds"].append(seed)
    synth["times_surfaced"] = len(synth["seeds"])
    synth["last_reinforced"] = now

    # Confidence grows with seeds, caps at 0.95
    synth["confidence"] = min(0.95, 0.3 + 0.15 * (len(synth["seeds"]) - 1))

    _save_synthesis(synth)
    _index_synthesis(synth)
    return synth


def update_status(synthesis_id: str, status: str) -> Dict:
    """Change synthesis status: dormant, activated, implemented, abandoned."""
    synth = _load_synthesis(synthesis_id)
    if not synth:
        raise ElaraNotFoundError(f"Synthesis {synthesis_id} not found.")

    if status not in ("dormant", "activated", "implemented", "abandoned"):
        raise ElaraValidationError("status must be 'dormant', 'activated', 'implemented', or 'abandoned'.")

    synth["status"] = status
    if status == "activated":
        synth["activated_at"] = datetime.now().isoformat()
    elif status == "implemented":
        synth["implemented_at"] = datetime.now().isoformat()
    elif status == "abandoned":
        synth["abandoned_at"] = datetime.now().isoformat()

    _save_synthesis(synth)
    _index_synthesis(synth)
    return synth


def get_synthesis(synthesis_id: str) -> Optional[Dict]:
    """Get a single synthesis by ID."""
    return _load_synthesis(synthesis_id)


def list_syntheses(
    status: Optional[str] = None,
    min_seeds: int = 0,
    n: int = 20,
) -> List[Dict]:
    """List syntheses, optionally filtered."""
    syntheses = _load_all_syntheses()

    if status:
        syntheses = [s for s in syntheses if s.get("status") == status]
    if min_seeds > 0:
        syntheses = [s for s in syntheses if len(s.get("seeds", [])) >= min_seeds]

    # Sort by confidence descending, then recency
    syntheses.sort(key=lambda s: (s.get("confidence", 0), s.get("last_reinforced", "")), reverse=True)
    return syntheses[:n]


# ============================================================================
# Auto-detection: find recurring ideas in new conversation exchanges
# ============================================================================

def check_for_recurring_ideas(exchanges: List[Dict], min_matches: int = 3) -> List[Dict]:
    """
    Given new conversation exchanges, check if any cluster with existing seeds.

    Each exchange should have: {"text": "...", "session_id": "...", "timestamp": "..."}

    Returns list of syntheses that got reinforced or newly created.
    """
    seed_collection = _get_seed_collection()
    if not seed_collection:
        return []

    reinforced = []

    for exchange in exchanges:
        text = exchange.get("text", "").strip()
        if not text or len(text) < 20:  # Skip very short exchanges
            continue

        # Search existing seeds for similarity
        try:
            count = seed_collection.count()
            if count == 0:
                continue

            results = seed_collection.query(
                query_texts=[text],
                n_results=min(5, count),
            )

            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            for i, seed_id in enumerate(ids):
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                if similarity >= SEED_SIMILARITY_THRESHOLD:
                    # Found a match — which synthesis does this seed belong to?
                    synth_id = metadatas[i].get("synthesis_id", "") if i < len(metadatas) else ""
                    if synth_id:
                        synth = _load_synthesis(synth_id)
                        if synth and synth.get("status") not in ("implemented", "abandoned"):
                            try:
                                result = add_seed(
                                    synth_id,
                                    quote=text[:200],
                                    source="conversation",
                                    source_id=exchange.get("session_id"),
                                )
                                reinforced.append(result)
                            except ElaraNotFoundError:
                                pass

        except Exception:
            continue

    return reinforced


def index_seed(synthesis_id: str, quote: str, seed_index: int):
    """Index an individual seed for cross-synthesis clustering."""
    seed_collection = _get_seed_collection()
    if not seed_collection:
        return

    seed_id = f"{synthesis_id}_{seed_index}"
    try:
        seed_collection.upsert(
            ids=[seed_id],
            documents=[quote],
            metadatas=[{"synthesis_id": synthesis_id}],
        )
    except Exception:
        pass


def reindex_all_seeds():
    """Rebuild seed index from all syntheses. Run at boot if needed."""
    syntheses = _load_all_syntheses()
    count = 0
    for synth in syntheses:
        _index_synthesis(synth)
        for i, seed in enumerate(synth.get("seeds", [])):
            index_seed(synth["synthesis_id"], seed.get("quote", ""), i)
            count += 1
    return count


# ============================================================================
# Analytics (for blind_spots and dreams integration)
# ============================================================================

def get_ready_ideas(min_seeds: int = 3) -> List[Dict]:
    """
    Ideas that have been reinforced enough to act on.
    Used at boot: "Recurring idea: [concept] (surfaced N times). Ready to build?"
    """
    syntheses = _load_all_syntheses()
    ready = []

    for s in syntheses:
        if s.get("status") in ("implemented", "abandoned"):
            continue
        if len(s.get("seeds", [])) >= min_seeds:
            ready.append({
                "synthesis_id": s["synthesis_id"],
                "concept": s["concept"],
                "times_surfaced": s.get("times_surfaced", 0),
                "confidence": s.get("confidence", 0),
                "first_seen": s.get("first_seen", ""),
                "last_reinforced": s.get("last_reinforced", ""),
                "status": s.get("status", "dormant"),
            })

    ready.sort(key=lambda x: x["confidence"], reverse=True)
    return ready


def get_synthesis_stats() -> Dict:
    """Summary stats for dreams integration."""
    syntheses = _load_all_syntheses()
    if not syntheses:
        return {"total": 0, "dormant": 0, "activated": 0, "implemented": 0, "abandoned": 0}

    by_status = {}
    for s in syntheses:
        status = s.get("status", "dormant")
        by_status[status] = by_status.get(status, 0) + 1

    total_seeds = sum(len(s.get("seeds", [])) for s in syntheses)

    return {
        "total": len(syntheses),
        "dormant": by_status.get("dormant", 0),
        "activated": by_status.get("activated", 0),
        "implemented": by_status.get("implemented", 0),
        "abandoned": by_status.get("abandoned", 0),
        "total_seeds": total_seeds,
        "avg_seeds": round(total_seeds / len(syntheses), 1) if syntheses else 0,
    }
