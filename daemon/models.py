# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Cognitive Models — Persistent understanding that accumulates over time.

Storage: ~/.elara/elara-models/ (JSON files, one per model)
Index:   ~/.elara/elara-models-db/ (ChromaDB, cosine similarity)

Models are statements of understanding about the world, the user, or work patterns.
They strengthen with confirming evidence, weaken with contradictions, and invalidate
when proven wrong. The overnight brain builds and checks these automatically.

Confidence mechanics:
  - supports:    +0.05 (slow build)
  - weakens:     -0.08 (faster erosion)
  - invalidates: -0.30 (sharp drop)
  - cap:         0.95 max (never fully certain)
  - time decay:  -0.05 per run if not checked in 30 days
"""

import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from core.paths import get_paths
from daemon.events import bus, Events
from daemon.schemas import (
    CognitiveModel, ModelEvidence, load_validated, save_validated,
    ElaraNotFoundError,
)

logger = logging.getLogger("elara.models")

_p = get_paths()
MODELS_DIR = _p.models_dir
MODELS_DB_DIR = _p.models_db

# Confidence adjustment constants
SUPPORTS_DELTA = 0.05
WEAKENS_DELTA = -0.08
INVALIDATES_DELTA = -0.30
MAX_CONFIDENCE = 0.95
MIN_CONFIDENCE = 0.0
TIME_DECAY_DELTA = -0.05
TIME_DECAY_DAYS = 30


# ============================================================================
# Storage layer (JSON files — source of truth)
# ============================================================================

def _ensure_dirs():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _model_path(model_id: str) -> Path:
    return MODELS_DIR / f"{model_id}.json"


def _generate_id(statement: str) -> str:
    raw = f"{statement}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_model(model_id: str) -> Optional[Dict]:
    path = _model_path(model_id)
    if not path.exists():
        return None
    model = load_validated(path, CognitiveModel)
    return model.model_dump()


def _save_model(model: Dict):
    _ensure_dirs()
    validated = CognitiveModel.model_validate(model)
    path = _model_path(model["model_id"])
    save_validated(path, validated)


def _load_all_models() -> List[Dict]:
    _ensure_dirs()
    models = []
    for p in sorted(MODELS_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                m = load_validated(p, CognitiveModel)
                models.append(m.model_dump())
            except Exception as e:
                logger.warning("Failed to load model %s: %s", p.name, e)
    return models


# ============================================================================
# ChromaDB index (semantic search over models)
# ============================================================================

_chroma_client = None
_chroma_collection = None


def _get_collection():
    global _chroma_client, _chroma_collection

    if not CHROMA_AVAILABLE:
        return None

    if _chroma_collection is not None:
        return _chroma_collection

    try:
        MODELS_DB_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(MODELS_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="elara_models",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to init models ChromaDB: %s", e)
        return None


def _index_model(model: Dict):
    collection = _get_collection()
    if not collection:
        return

    parts = [model.get("statement", "")]
    for ev in model.get("evidence", []):
        parts.append(ev.get("text", ""))
    parts.extend(model.get("tags", []))

    text = " ".join(p for p in parts if p)
    if not text.strip():
        return

    metadata = {
        "domain": model.get("domain", "general"),
        "status": model.get("status", "active"),
        "confidence": model.get("confidence", 0.5),
        "created": model.get("created", ""),
    }

    try:
        collection.upsert(
            ids=[model["model_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception as e:
        logger.warning("Failed to index model %s: %s", model.get("model_id", "?"), e)


# ============================================================================
# Core operations
# ============================================================================

def create_model(
    statement: str,
    domain: str = "general",
    evidence_text: Optional[str] = None,
    confidence: float = 0.5,
    source_run: str = "",
    tags: Optional[List[str]] = None,
) -> Dict:
    """Create a new cognitive model — a statement of understanding."""
    logger.info("Creating model [%s]: %s", domain, statement[:80])
    model_id = _generate_id(statement)
    now = datetime.now().isoformat()

    evidence = []
    if evidence_text:
        evidence.append(ModelEvidence(
            text=evidence_text,
            source="manual" if not source_run else "overnight",
            direction="supports",
            date=now,
        ).model_dump())

    model = CognitiveModel(
        model_id=model_id,
        statement=statement,
        domain=domain,
        confidence=min(round(confidence, 2), MAX_CONFIDENCE),
        evidence=evidence,
        status="active",
        check_count=0,
        strengthen_count=1 if evidence_text else 0,
        weaken_count=0,
        created=now,
        last_updated=now,
        last_checked=now,
        source_run=source_run,
        tags=tags or [],
    ).model_dump()

    _save_model(model)
    _index_model(model)
    bus.emit(Events.MODEL_CREATED, {
        "model_id": model_id,
        "statement": statement[:200],
        "domain": domain,
        "confidence": confidence,
    }, source="models")
    return model


def add_evidence(
    model_id: str,
    text: str,
    source: str = "overnight",
    direction: str = "supports",
) -> Dict:
    """
    Add evidence to an existing model, adjusting confidence.

    direction: "supports" (+0.05), "weakens" (-0.08), "invalidates" (-0.30)
    """
    model = _load_model(model_id)
    if not model:
        raise ElaraNotFoundError(f"Model {model_id} not found.")

    now = datetime.now().isoformat()

    # Add evidence
    ev = ModelEvidence(
        text=text,
        source=source,
        direction=direction,
        date=now,
    ).model_dump()
    model["evidence"].append(ev)

    # Adjust confidence
    if direction == "supports":
        delta = SUPPORTS_DELTA
        model["strengthen_count"] = model.get("strengthen_count", 0) + 1
    elif direction == "weakens":
        delta = WEAKENS_DELTA
        model["weaken_count"] = model.get("weaken_count", 0) + 1
        if model["confidence"] + delta < 0.3:
            model["status"] = "weakened"
    elif direction == "invalidates":
        delta = INVALIDATES_DELTA
        model["weaken_count"] = model.get("weaken_count", 0) + 1
        model["status"] = "invalidated"
    else:
        delta = 0.0

    model["confidence"] = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, round(model["confidence"] + delta, 2)))
    model["last_updated"] = now
    model["last_checked"] = now
    model["check_count"] = model.get("check_count", 0) + 1

    _save_model(model)
    _index_model(model)

    bus.emit(Events.MODEL_UPDATED, {
        "model_id": model_id,
        "direction": direction,
        "new_confidence": model["confidence"],
        "status": model["status"],
    }, source="models")

    if model["status"] == "invalidated":
        bus.emit(Events.MODEL_INVALIDATED, {
            "model_id": model_id,
            "statement": model["statement"][:200],
        }, source="models")

    return model


def check_model(model_id: str) -> Dict:
    """Increment check_count and update last_checked (without adding evidence)."""
    model = _load_model(model_id)
    if not model:
        raise ElaraNotFoundError(f"Model {model_id} not found.")

    model["check_count"] = model.get("check_count", 0) + 1
    model["last_checked"] = datetime.now().isoformat()
    _save_model(model)
    return model


def invalidate_model(model_id: str) -> Dict:
    """Directly invalidate a model."""
    model = _load_model(model_id)
    if not model:
        raise ElaraNotFoundError(f"Model {model_id} not found.")

    logger.info("Invalidating model %s: %s", model_id, model["statement"][:60])
    model["status"] = "invalidated"
    model["last_updated"] = datetime.now().isoformat()
    _save_model(model)
    _index_model(model)

    bus.emit(Events.MODEL_INVALIDATED, {
        "model_id": model_id,
        "statement": model["statement"][:200],
    }, source="models")
    return model


def get_active_models(
    domain: Optional[str] = None,
    min_confidence: float = 0.3,
) -> List[Dict]:
    """Get all active models, optionally filtered by domain and confidence."""
    models = _load_all_models()
    active = [
        m for m in models
        if m.get("status") == "active"
        and m.get("confidence", 0) >= min_confidence
    ]
    if domain:
        active = [m for m in active if m.get("domain") == domain]
    active.sort(key=lambda m: m.get("confidence", 0), reverse=True)
    return active


def search_models(query: str, n: int = 5) -> List[Dict]:
    """Semantic search across models via ChromaDB."""
    collection = _get_collection()
    if not collection:
        return _keyword_search_models(query, n)

    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n, count),
        )

        models = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, model_id in enumerate(ids):
            model = _load_model(model_id)
            if model:
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                model["_similarity"] = round(similarity, 3)
                models.append(model)

        return models
    except Exception as e:
        logger.warning("ChromaDB model search failed: %s", e)
        return _keyword_search_models(query, n)


def _keyword_search_models(query: str, n: int) -> List[Dict]:
    """Keyword fallback for model search."""
    query_words = set(query.lower().split())
    models = _load_all_models()
    scored = []
    for m in models:
        text = f"{m.get('statement','')} {m.get('domain','')} {' '.join(m.get('tags',[]))}".lower()
        overlap = len(query_words & set(text.split()))
        if overlap > 0:
            scored.append((overlap, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:n]]


def list_models(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    n: int = 50,
) -> List[Dict]:
    """List models, optionally filtered."""
    models = _load_all_models()

    if status:
        models = [m for m in models if m.get("status") == status]
    if domain:
        models = [m for m in models if m.get("domain") == domain]

    models.sort(key=lambda m: m.get("last_updated", ""), reverse=True)
    return models[:n]


def get_model(model_id: str) -> Optional[Dict]:
    """Get a single model by ID."""
    return _load_model(model_id)


def get_model_stats() -> Dict:
    """Aggregate stats across all models."""
    models = _load_all_models()
    if not models:
        return {
            "total": 0,
            "by_status": {},
            "by_domain": {},
            "avg_confidence": None,
        }

    by_status = {}
    by_domain = {}
    confidences = []

    for m in models:
        s = m.get("status", "active")
        by_status[s] = by_status.get(s, 0) + 1

        d = m.get("domain", "general")
        by_domain[d] = by_domain.get(d, 0) + 1

        if s == "active":
            confidences.append(m.get("confidence", 0.5))

    return {
        "total": len(models),
        "by_status": by_status,
        "by_domain": by_domain,
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
    }


def apply_time_decay() -> List[Dict]:
    """
    Apply confidence decay to models not checked in TIME_DECAY_DAYS days.
    Called by overnight brain. Returns list of decayed models.
    """
    models = _load_all_models()
    cutoff = datetime.now() - timedelta(days=TIME_DECAY_DAYS)
    decayed = []

    for m in models:
        if m.get("status") != "active":
            continue

        last_checked = m.get("last_checked", "")
        if not last_checked:
            continue

        try:
            last_dt = datetime.fromisoformat(last_checked)
            if last_dt < cutoff:
                m["confidence"] = max(MIN_CONFIDENCE, round(m["confidence"] + TIME_DECAY_DELTA, 2))
                m["last_updated"] = datetime.now().isoformat()
                if m["confidence"] < 0.3:
                    m["status"] = "weakened"
                _save_model(m)
                _index_model(m)
                decayed.append(m)
        except (ValueError, TypeError):
            pass

    if decayed:
        logger.info("Time decay applied to %d models", len(decayed))
    return decayed


def reindex_all() -> Dict:
    """Rebuild ChromaDB index from JSON files."""
    models = _load_all_models()
    for m in models:
        _index_model(m)
    return {"indexed": len(models)}
