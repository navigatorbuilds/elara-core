# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Predictions — Explicit forecasts with deadlines and verification.

Storage: ~/.elara/elara-predictions/ (JSON files, one per prediction)
Index:   ~/.elara/elara-predictions-db/ (ChromaDB, cosine similarity)

The overnight brain makes predictions based on cognitive models.
When deadlines pass, predictions get checked against reality.
Accuracy rates over time calibrate the brain's confidence.

This closes the foresight loop:
  model → prediction → deadline → check → lesson → model update
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
    Prediction, load_validated, save_validated,
    ElaraNotFoundError, ElaraValidationError,
)

logger = logging.getLogger("elara.predictions")

_p = get_paths()
PREDICTIONS_DIR = _p.predictions_dir
PREDICTIONS_DB_DIR = _p.predictions_db


# ============================================================================
# Storage layer (JSON files — source of truth)
# ============================================================================

def _ensure_dirs():
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)


def _prediction_path(prediction_id: str) -> Path:
    return PREDICTIONS_DIR / f"{prediction_id}.json"


def _generate_id(statement: str) -> str:
    raw = f"{statement}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_prediction(prediction_id: str) -> Optional[Dict]:
    path = _prediction_path(prediction_id)
    if not path.exists():
        return None
    model = load_validated(path, Prediction)
    return model.model_dump()


def _save_prediction(prediction: Dict):
    _ensure_dirs()
    validated = Prediction.model_validate(prediction)
    path = _prediction_path(prediction["prediction_id"])
    save_validated(path, validated)


def _load_all_predictions() -> List[Dict]:
    _ensure_dirs()
    predictions = []
    for p in sorted(PREDICTIONS_DIR.glob("*.json")):
        if p.suffix == ".json" and not p.name.endswith(".tmp"):
            try:
                m = load_validated(p, Prediction)
                predictions.append(m.model_dump())
            except Exception as e:
                logger.warning("Failed to load prediction %s: %s", p.name, e)
    return predictions


# ============================================================================
# ChromaDB index (semantic search over predictions)
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
        PREDICTIONS_DB_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(PREDICTIONS_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="elara_predictions",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to init predictions ChromaDB: %s", e)
        return None


def _index_prediction(prediction: Dict):
    collection = _get_collection()
    if not collection:
        return

    parts = [
        prediction.get("statement", ""),
        prediction.get("actual_outcome", "") or "",
        prediction.get("lesson", "") or "",
    ]
    parts.extend(prediction.get("tags", []))

    text = " ".join(p for p in parts if p)
    if not text.strip():
        return

    metadata = {
        "status": prediction.get("status", "pending"),
        "confidence": prediction.get("confidence", 0.5),
        "deadline": prediction.get("deadline", ""),
        "created": prediction.get("created", ""),
    }

    try:
        collection.upsert(
            ids=[prediction["prediction_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception as e:
        logger.warning("Failed to index prediction %s: %s", prediction.get("prediction_id", "?"), e)


# ============================================================================
# Core operations
# ============================================================================

def make_prediction(
    statement: str,
    confidence: float = 0.5,
    deadline: str = "",
    source_model: Optional[str] = None,
    source_run: str = "",
    tags: Optional[List[str]] = None,
) -> Dict:
    """Make an explicit prediction with a deadline."""
    logger.info("Making prediction (conf=%.2f): %s", confidence, statement[:80])

    if not deadline:
        # Default: 14 days from now
        deadline = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    prediction_id = _generate_id(statement)
    now = datetime.now().isoformat()

    prediction = Prediction(
        prediction_id=prediction_id,
        statement=statement,
        confidence=min(round(confidence, 2), 0.95),
        deadline=deadline,
        source_model=source_model,
        source_run=source_run,
        status="pending",
        actual_outcome=None,
        lesson=None,
        checked=None,
        created=now,
        tags=tags or [],
    ).model_dump()

    _save_prediction(prediction)
    _index_prediction(prediction)

    bus.emit(Events.PREDICTION_MADE, {
        "prediction_id": prediction_id,
        "statement": statement[:200],
        "confidence": confidence,
        "deadline": deadline,
    }, source="predictions")

    return prediction


def check_prediction(
    prediction_id: str,
    actual_outcome: str,
    status: str,
    lesson: Optional[str] = None,
) -> Dict:
    """
    Check a prediction against reality.

    status: "correct", "wrong", "partially_correct", "expired"
    """
    prediction = _load_prediction(prediction_id)
    if not prediction:
        raise ElaraNotFoundError(f"Prediction {prediction_id} not found.")

    valid_statuses = ("correct", "wrong", "partially_correct", "expired")
    if status not in valid_statuses:
        raise ElaraValidationError(f"status must be one of: {', '.join(valid_statuses)}")

    logger.info("Checking prediction %s: %s", prediction_id, status)

    prediction["actual_outcome"] = actual_outcome
    prediction["status"] = status
    prediction["lesson"] = lesson
    prediction["checked"] = datetime.now().isoformat()

    _save_prediction(prediction)
    _index_prediction(prediction)

    bus.emit(Events.PREDICTION_CHECKED, {
        "prediction_id": prediction_id,
        "status": status,
        "was_correct": status == "correct",
    }, source="predictions")

    return prediction


def check_expired_predictions() -> List[Dict]:
    """
    Find predictions whose deadline has passed but status is still pending.
    Returns them for manual or overnight verification.
    """
    predictions = _load_all_predictions()
    now = datetime.now()
    expired = []

    for p in predictions:
        if p.get("status") != "pending":
            continue
        deadline_str = p.get("deadline", "")
        if not deadline_str:
            continue
        try:
            deadline = datetime.fromisoformat(deadline_str)
            if deadline < now:
                p["_days_overdue"] = (now - deadline).days
                expired.append(p)
        except (ValueError, TypeError):
            pass

    expired.sort(key=lambda p: p.get("_days_overdue", 0), reverse=True)
    return expired


def get_pending_predictions(days_ahead: int = 14) -> List[Dict]:
    """Get predictions with upcoming deadlines."""
    predictions = _load_all_predictions()
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)
    pending = []

    for p in predictions:
        if p.get("status") != "pending":
            continue
        deadline_str = p.get("deadline", "")
        if not deadline_str:
            pending.append(p)
            continue
        try:
            deadline = datetime.fromisoformat(deadline_str)
            if deadline <= cutoff:
                days_left = (deadline - now).days
                p["_days_until_deadline"] = days_left
                pending.append(p)
        except (ValueError, TypeError):
            pending.append(p)

    pending.sort(key=lambda p: p.get("deadline", "9999"))
    return pending


def get_prediction_accuracy() -> Dict:
    """Calculate prediction accuracy rates over time."""
    predictions = _load_all_predictions()
    checked = [p for p in predictions if p.get("status") != "pending"]
    pending = [p for p in predictions if p.get("status") == "pending"]

    if not checked:
        return {
            "total": len(predictions),
            "checked": 0,
            "pending": len(pending),
            "correct": 0,
            "wrong": 0,
            "partially_correct": 0,
            "expired": 0,
            "accuracy": None,
            "avg_confidence": None,
            "calibration": None,
        }

    correct = [p for p in checked if p.get("status") == "correct"]
    wrong = [p for p in checked if p.get("status") == "wrong"]
    partial = [p for p in checked if p.get("status") == "partially_correct"]
    expired = [p for p in checked if p.get("status") == "expired"]

    # Accuracy: correct=1, partial=0.5, wrong/expired=0
    score = len(correct) + 0.5 * len(partial)
    accuracy = round(score / len(checked), 2) if checked else None

    # Calibration: avg predicted confidence vs actual accuracy
    avg_confidence = None
    if checked:
        avg_confidence = round(sum(p.get("confidence", 0.5) for p in checked) / len(checked), 2)

    return {
        "total": len(predictions),
        "checked": len(checked),
        "pending": len(pending),
        "correct": len(correct),
        "wrong": len(wrong),
        "partially_correct": len(partial),
        "expired": len(expired),
        "accuracy": accuracy,
        "avg_confidence": avg_confidence,
        "calibration": round(accuracy - avg_confidence, 2) if accuracy is not None and avg_confidence is not None else None,
    }


def list_predictions(
    status: Optional[str] = None,
    n: int = 50,
) -> List[Dict]:
    """List predictions, optionally filtered by status."""
    predictions = _load_all_predictions()

    if status:
        predictions = [p for p in predictions if p.get("status") == status]

    predictions.sort(key=lambda p: p.get("created", ""), reverse=True)
    return predictions[:n]


def get_prediction(prediction_id: str) -> Optional[Dict]:
    """Get a single prediction by ID."""
    return _load_prediction(prediction_id)


def search_predictions(query: str, n: int = 5) -> List[Dict]:
    """Semantic search across predictions via ChromaDB."""
    collection = _get_collection()
    if not collection:
        return _keyword_search_predictions(query, n)

    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n, count),
        )

        predictions = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, pred_id in enumerate(ids):
            pred = _load_prediction(pred_id)
            if pred:
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                pred["_similarity"] = round(similarity, 3)
                predictions.append(pred)

        return predictions
    except Exception as e:
        logger.warning("ChromaDB prediction search failed: %s", e)
        return _keyword_search_predictions(query, n)


def _keyword_search_predictions(query: str, n: int) -> List[Dict]:
    """Keyword fallback for prediction search."""
    query_words = set(query.lower().split())
    predictions = _load_all_predictions()
    scored = []
    for p in predictions:
        text = f"{p.get('statement','')} {' '.join(p.get('tags',[]))}".lower()
        overlap = len(query_words & set(text.split()))
        if overlap > 0:
            scored.append((overlap, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:n]]


def reindex_all() -> Dict:
    """Rebuild ChromaDB index from JSON files."""
    predictions = _load_all_predictions()
    for p in predictions:
        _index_prediction(p)
    return {"indexed": len(predictions)}
