# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Principles — Crystallized self-derived rules from repeated insights.

Storage: ~/.elara/elara-principles.json (JSON list, like corrections)
Index:   ~/.elara/elara-principles-db/ (ChromaDB, cosine similarity)

Principles emerge when the same insight appears 3+ times across overnight runs.
They represent wisdom — high-level rules that should guide behavior.

The crystallization loop:
  overnight insight → check similarity to past insights → 3+ matches → principle
  principle + new evidence → confirm (strengthen) or challenge (weaken)
"""

import logging
import hashlib
from datetime import datetime
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
    Principle, load_validated_list, save_validated_list,
    ElaraNotFoundError,
)

logger = logging.getLogger("elara.principles")

_p = get_paths()
PRINCIPLES_FILE = _p.principles_file
PRINCIPLES_DB_DIR = _p.principles_db

# Confidence mechanics
CONFIRM_DELTA = 0.05
CHALLENGE_DELTA = -0.10
MAX_CONFIDENCE = 0.95
CRYSTALLIZATION_THRESHOLD = 3  # How many similar insights before crystallizing


# ============================================================================
# Storage layer (JSON list file — source of truth)
# ============================================================================

def _load() -> List[Dict]:
    models = load_validated_list(PRINCIPLES_FILE, Principle)
    return [m.model_dump() for m in models]


def _save(principles: List[Dict]):
    models = [Principle.model_validate(p) for p in principles]
    save_validated_list(PRINCIPLES_FILE, models)


def _generate_id(statement: str) -> str:
    raw = f"{statement}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ============================================================================
# ChromaDB index (semantic search for crystallization + retrieval)
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
        PRINCIPLES_DB_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(PRINCIPLES_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="elara_principles",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to init principles ChromaDB: %s", e)
        return None


def _index_principle(principle: Dict):
    collection = _get_collection()
    if not collection:
        return

    parts = [
        principle.get("statement", ""),
        principle.get("domain", ""),
    ]
    parts.extend(principle.get("tags", []))

    text = " ".join(p for p in parts if p)
    if not text.strip():
        return

    metadata = {
        "domain": principle.get("domain", "general"),
        "status": principle.get("status", "active"),
        "confidence": principle.get("confidence", 0.5),
        "created": principle.get("created", ""),
        "times_confirmed": principle.get("times_confirmed", 0),
    }

    try:
        collection.upsert(
            ids=[principle["principle_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception as e:
        logger.warning("Failed to index principle %s: %s", principle.get("principle_id", "?"), e)


def _sync_all_to_chroma(principles: List[Dict]):
    """Bulk sync all principles to ChromaDB."""
    collection = _get_collection()
    if not collection or not principles:
        return

    ids = []
    documents = []
    metadatas = []

    for p in principles:
        pid = p.get("principle_id", "")
        if not pid:
            continue
        text = f"{p.get('statement', '')} {p.get('domain', '')} {' '.join(p.get('tags', []))}"
        if not text.strip():
            continue

        ids.append(pid)
        documents.append(text)
        metadatas.append({
            "domain": p.get("domain", "general"),
            "status": p.get("status", "active"),
            "confidence": p.get("confidence", 0.5),
            "created": p.get("created", ""),
            "times_confirmed": p.get("times_confirmed", 0),
        })

    if ids:
        try:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        except Exception as e:
            logger.warning("Principles bulk sync failed: %s", e)


# ============================================================================
# Core operations
# ============================================================================

def create_principle(
    statement: str,
    domain: str = "general",
    source_insights: Optional[List[str]] = None,
    source_models: Optional[List[str]] = None,
    confidence: float = 0.5,
    tags: Optional[List[str]] = None,
) -> Dict:
    """Create a new crystallized principle."""
    logger.info("Creating principle [%s]: %s", domain, statement[:80])

    principle_id = _generate_id(statement)
    now = datetime.now().isoformat()

    principle = Principle(
        principle_id=principle_id,
        statement=statement,
        domain=domain,
        confidence=min(round(confidence, 2), MAX_CONFIDENCE),
        source_insights=source_insights or [],
        source_models=source_models or [],
        status="active",
        times_confirmed=0,
        times_challenged=0,
        last_confirmed=None,
        created=now,
        tags=tags or [],
    ).model_dump()

    principles = _load()
    principles.append(principle)
    _save(principles)
    _index_principle(principle)

    bus.emit(Events.PRINCIPLE_CRYSTALLIZED, {
        "principle_id": principle_id,
        "statement": statement[:200],
        "domain": domain,
    }, source="principles")

    return principle


def confirm_principle(principle_id: str, run_date: Optional[str] = None) -> Dict:
    """Confirm a principle — seen again, boost confidence."""
    principles = _load()
    target = None
    for p in principles:
        if p.get("principle_id") == principle_id:
            target = p
            break

    if not target:
        raise ElaraNotFoundError(f"Principle {principle_id} not found.")

    now = datetime.now().isoformat()
    target["times_confirmed"] = target.get("times_confirmed", 0) + 1
    target["last_confirmed"] = now
    target["confidence"] = min(MAX_CONFIDENCE, round(target.get("confidence", 0.5) + CONFIRM_DELTA, 2))

    if run_date and run_date not in target.get("source_insights", []):
        target["source_insights"].append(run_date)

    _save(principles)
    _index_principle(target)

    bus.emit(Events.PRINCIPLE_CONFIRMED, {
        "principle_id": principle_id,
        "times_confirmed": target["times_confirmed"],
        "confidence": target["confidence"],
    }, source="principles")

    return target


def challenge_principle(principle_id: str, evidence: Optional[str] = None) -> Dict:
    """Challenge a principle — contradicting evidence, lower confidence."""
    principles = _load()
    target = None
    for p in principles:
        if p.get("principle_id") == principle_id:
            target = p
            break

    if not target:
        raise ElaraNotFoundError(f"Principle {principle_id} not found.")

    target["times_challenged"] = target.get("times_challenged", 0) + 1
    target["confidence"] = max(0.0, round(target.get("confidence", 0.5) + CHALLENGE_DELTA, 2))

    if target["confidence"] < 0.2:
        target["status"] = "challenged"

    _save(principles)
    _index_principle(target)

    bus.emit(Events.PRINCIPLE_CHALLENGED, {
        "principle_id": principle_id,
        "times_challenged": target["times_challenged"],
        "confidence": target["confidence"],
        "status": target["status"],
    }, source="principles")

    return target


def get_active_principles(domain: Optional[str] = None) -> List[Dict]:
    """Get all active principles, optionally filtered by domain."""
    principles = _load()
    active = [p for p in principles if p.get("status") == "active"]
    if domain:
        active = [p for p in active if p.get("domain") == domain]
    active.sort(key=lambda p: p.get("confidence", 0), reverse=True)
    return active


def check_for_crystallization(
    insight_text: str,
    source_run: str = "",
    similarity_threshold: float = 0.65,
) -> Optional[Dict]:
    """
    Check if an insight should crystallize into a principle.

    Searches ChromaDB for similar past principles/insights.
    If 3+ matches exist above threshold, a principle might already exist
    (in which case confirm it) or should be created.

    Returns the confirmed/new principle, or None if not enough matches.
    """
    collection = _get_collection()
    if not collection:
        return None

    try:
        count = collection.count()
        if count == 0:
            return None

        results = collection.query(
            query_texts=[insight_text],
            n_results=min(5, count),
        )

        if not results["ids"] or not results["ids"][0]:
            return None

        # Check for high-similarity matches
        ids = results["ids"][0]
        distances = results.get("distances", [[]])[0]
        matches = []

        for i, pid in enumerate(ids):
            similarity = 1.0 - distances[i] if i < len(distances) else 0.0
            if similarity >= similarity_threshold:
                matches.append({"id": pid, "similarity": similarity})

        if not matches:
            return None

        # If we found an existing principle with high match, confirm it
        principles = _load()
        for match in matches:
            for p in principles:
                if p.get("principle_id") == match["id"]:
                    logger.info("Confirming existing principle %s (sim=%.2f)", match["id"], match["similarity"])
                    return confirm_principle(match["id"], run_date=source_run)

        # Not enough matches for crystallization yet (would need 3+ from insights DB)
        # This function is a building block — the overnight brain calls it after
        # accumulating insights across runs
        return None

    except Exception as e:
        logger.warning("Crystallization check failed: %s", e)
        return None


def search_principles(query: str, n: int = 5) -> List[Dict]:
    """Semantic search across principles."""
    collection = _get_collection()
    if not collection:
        return _keyword_search(query, n)

    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n, count),
        )

        found = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        principles = _load()
        principle_map = {p["principle_id"]: p for p in principles}

        for i, pid in enumerate(ids):
            if pid in principle_map:
                p = principle_map[pid].copy()
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                p["_similarity"] = round(similarity, 3)
                found.append(p)

        return found
    except Exception as e:
        logger.warning("ChromaDB principle search failed: %s", e)
        return _keyword_search(query, n)


def _keyword_search(query: str, n: int) -> List[Dict]:
    """Keyword fallback."""
    query_words = set(query.lower().split())
    principles = _load()
    scored = []
    for p in principles:
        text = f"{p.get('statement','')} {p.get('domain','')} {' '.join(p.get('tags',[]))}".lower()
        overlap = len(query_words & set(text.split()))
        if overlap > 0:
            scored.append((overlap, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:n]]


def get_principle(principle_id: str) -> Optional[Dict]:
    """Get a single principle by ID."""
    principles = _load()
    for p in principles:
        if p.get("principle_id") == principle_id:
            return p
    return None


def list_principles(
    status: Optional[str] = None,
    domain: Optional[str] = None,
) -> List[Dict]:
    """List all principles, optionally filtered."""
    principles = _load()
    if status:
        principles = [p for p in principles if p.get("status") == status]
    if domain:
        principles = [p for p in principles if p.get("domain") == domain]
    principles.sort(key=lambda p: p.get("confidence", 0), reverse=True)
    return principles


def get_principle_stats() -> Dict:
    """Aggregate stats across all principles."""
    principles = _load()
    if not principles:
        return {
            "total": 0,
            "by_status": {},
            "by_domain": {},
            "avg_confidence": None,
            "total_confirmations": 0,
            "total_challenges": 0,
        }

    by_status = {}
    by_domain = {}
    confidences = []
    total_confirmed = 0
    total_challenged = 0

    for p in principles:
        s = p.get("status", "active")
        by_status[s] = by_status.get(s, 0) + 1

        d = p.get("domain", "general")
        by_domain[d] = by_domain.get(d, 0) + 1

        if s == "active":
            confidences.append(p.get("confidence", 0.5))

        total_confirmed += p.get("times_confirmed", 0)
        total_challenged += p.get("times_challenged", 0)

    return {
        "total": len(principles),
        "by_status": by_status,
        "by_domain": by_domain,
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "total_confirmations": total_confirmed,
        "total_challenges": total_challenged,
    }


def reindex_all() -> Dict:
    """Rebuild ChromaDB index from JSON file."""
    principles = _load()
    _sync_all_to_chroma(principles)
    return {"indexed": len(principles)}
