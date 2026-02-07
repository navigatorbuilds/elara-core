"""
Elara Corrections System v2 — Learn from mistakes, know when they apply.

Storage: ~/.claude/elara-corrections.json (JSON, append-only, never decays)
Index:   ~/.claude/elara-corrections-db/ (ChromaDB, semantic search)

v2 upgrades:
- correction_type: "tendency" (behavioral) vs "technical" (code/task patterns)
- fails_when / fine_when: Contextual conditions — avoids overgeneralization
- Activation tracking: last_activated, times_surfaced, times_dismissed
- ChromaDB semantic search: match corrections to current task context
- Dormant detection: corrections that never fire (for blind_spots)
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
from daemon.schemas import Correction, load_validated_list, save_validated_list

logger = logging.getLogger("elara.corrections")

_p = get_paths()
CORRECTIONS_FILE = _p.corrections_file
CORRECTIONS_DB_DIR = _p.corrections_db
MAX_CORRECTIONS = 50


# ============================================================================
# Storage layer (JSON file — source of truth)
# ============================================================================

def _load() -> List[Dict]:
    models = load_validated_list(CORRECTIONS_FILE, Correction)
    return [m.model_dump() for m in models]


def _save(corrections: List[Dict]):
    models = [Correction.model_validate(c) for c in corrections]
    save_validated_list(CORRECTIONS_FILE, models)


# ============================================================================
# ChromaDB index layer (semantic search)
# ============================================================================

_chroma_client = None
_chroma_collection = None


def _get_collection():
    """Get or create the corrections ChromaDB collection."""
    global _chroma_client, _chroma_collection

    if not CHROMA_AVAILABLE:
        return None

    if _chroma_collection is not None:
        return _chroma_collection

    CORRECTIONS_DB_DIR.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(CORRECTIONS_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )
    _chroma_collection = _chroma_client.get_or_create_collection(
        name="elara_corrections",
        metadata={
            "description": "Elara's corrections — semantic mistake matching",
            "hnsw:space": "cosine",
        }
    )
    return _chroma_collection


def _correction_id(entry: Dict) -> str:
    """Stable ID from correction content."""
    content = f"{entry['id']}:{entry['mistake']}:{entry['correction']}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _index_text(entry: Dict) -> str:
    """Build the searchable text for a correction."""
    parts = [entry["mistake"], entry["correction"]]
    if entry.get("context"):
        parts.append(entry["context"])
    if entry.get("fails_when"):
        parts.append(f"Fails when: {entry['fails_when']}")
    if entry.get("fine_when"):
        parts.append(f"Fine when: {entry['fine_when']}")
    return " | ".join(parts)


def _sync_to_chroma(corrections: List[Dict]):
    """Sync all corrections to ChromaDB. Idempotent."""
    collection = _get_collection()
    if not collection:
        return
    logger.debug("Syncing %d corrections to ChromaDB", len(corrections))

    ids = []
    documents = []
    metadatas = []

    for entry in corrections:
        cid = _correction_id(entry)
        ids.append(cid)
        documents.append(_index_text(entry))
        metadatas.append({
            "correction_id": entry["id"],
            "correction_type": entry.get("correction_type", "tendency"),
            "date": entry.get("date", ""),
            "times_surfaced": entry.get("times_surfaced", 0),
        })

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


# ============================================================================
# Public API
# ============================================================================

def add_correction(
    mistake: str,
    correction: str,
    context: Optional[str] = None,
    correction_type: str = "tendency",
    fails_when: Optional[str] = None,
    fine_when: Optional[str] = None,
) -> Dict:
    """
    Record a correction with v2 contextual fields.

    Args:
        mistake: What went wrong
        correction: What's actually correct
        context: When/why this happened
        correction_type: "tendency" (behavioral) or "technical" (code pattern)
        fails_when: Condition when this mistake applies
        fine_when: Condition when this pattern is actually correct
    """
    logger.info("Adding %s correction: %s", correction_type, mistake[:80])
    corrections = _load()

    entry = Correction(
        id=len(corrections) + 1,
        mistake=mistake,
        correction=correction,
        context=context,
        correction_type=correction_type,
        fails_when=fails_when,
        fine_when=fine_when,
        date=datetime.now().isoformat(),
        last_activated=None,
        times_surfaced=0,
        times_dismissed=0,
    ).model_dump()
    corrections.append(entry)

    # Cap at MAX_CORRECTIONS, remove oldest
    if len(corrections) > MAX_CORRECTIONS:
        corrections = corrections[-MAX_CORRECTIONS:]

    _save(corrections)

    # Index in ChromaDB
    _sync_to_chroma([entry])

    bus.emit(Events.CORRECTION_ADDED, {
        "id": entry["id"],
        "mistake": mistake,
        "correction_type": correction_type,
    }, source="corrections")

    return entry


def list_corrections(n: int = 20) -> List[Dict]:
    """Get recent corrections."""
    corrections = _load()
    return corrections[-n:]


def search_corrections(keyword: str) -> List[Dict]:
    """Simple keyword search through corrections."""
    corrections = _load()
    keyword_lower = keyword.lower()
    return [
        c for c in corrections
        if keyword_lower in c["mistake"].lower()
        or keyword_lower in c["correction"].lower()
        or keyword_lower in (c.get("context") or "").lower()
    ]


class CorrectionSearchError(Exception):
    """Raised when correction search fails — corrections should fail loud."""
    pass


def check_corrections(task_description: str, n_results: int = 3) -> List[Dict]:
    """
    Semantic search: find corrections relevant to current task context.

    This is the activation function — it finds corrections that MATCH
    what you're about to do, not just keyword overlap.

    FAILURE MODE: LOUD. If ChromaDB fails, returns error info in results
    so the caller knows corrections couldn't be checked. Corrections exist
    to prevent repeated mistakes — silent failure defeats the purpose.

    Returns corrections with their conditions (fails_when/fine_when)
    so the caller can decide whether to heed the warning.
    """
    collection = _get_collection()

    if not collection or collection.count() == 0:
        # Fall back to keyword search
        logger.warning("ChromaDB not available for corrections, falling back to keyword search")
        return search_corrections(task_description)

    # Ensure index is current
    corrections = _load()
    _sync_to_chroma(corrections)

    try:
        results = collection.query(
            query_texts=[task_description],
            n_results=min(n_results, collection.count()),
        )
    except Exception as e:
        # LOUD failure — return a warning entry so caller sees the problem
        logger.error("ChromaDB correction search failed: %s", e)
        return [{
            "id": -1,
            "mistake": "[CORRECTIONS SEARCH FAILED]",
            "correction": f"ChromaDB error: {e}. Falling back to keyword search.",
            "correction_type": "system_error",
            "relevance": 1.0,
            "_error": True,
        }] + search_corrections(task_description)

    if not results["documents"] or not results["documents"][0]:
        return []

    matched = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        distance = results["distances"][0][i] if results["distances"] else 1.0

        relevance = max(0, 1 - distance)

        # Only return if reasonably relevant (cosine similarity > 0.25)
        if relevance < 0.25:
            continue

        # Find the full correction entry
        correction_id = meta.get("correction_id")
        full_entry = None
        for c in corrections:
            if c["id"] == correction_id:
                full_entry = c.copy()
                break

        if not full_entry:
            continue

        full_entry["relevance"] = round(relevance, 3)
        matched.append(full_entry)

    return matched


def record_activation(correction_id: int, was_relevant: bool = True):
    """
    Track that a correction was surfaced during work.

    Args:
        correction_id: The correction's ID
        was_relevant: True if it was useful, False if dismissed
    """
    corrections = _load()

    for entry in corrections:
        if entry["id"] == correction_id:
            entry["last_activated"] = datetime.now().isoformat()
            entry["times_surfaced"] = entry.get("times_surfaced", 0) + 1
            if not was_relevant:
                entry["times_dismissed"] = entry.get("times_dismissed", 0) + 1
            break

    _save(corrections)


def get_dormant_corrections(days: int = 14) -> List[Dict]:
    """
    Find corrections that have never been activated or haven't
    been activated in `days` days. Used by blind_spots().
    """
    corrections = _load()

    dormant = []
    cutoff = datetime.now() - timedelta(days=days)

    for entry in corrections:
        last = entry.get("last_activated")

        if last is None:
            # Never activated
            dormant.append(entry)
        else:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt < cutoff:
                    dormant.append(entry)
            except (ValueError, TypeError):
                dormant.append(entry)

    return dormant


# ============================================================================
# Boot functions
# ============================================================================

def boot_corrections(n: int = 10) -> str:
    """
    Get corrections for boot loading. Short format.
    Tendencies always show. Technical only if recently active.
    """
    corrections = _load()

    # Always show tendencies (behavioral habits)
    tendencies = [c for c in corrections if c.get("correction_type") != "technical"]

    # Only show technical corrections if recently activated (last 7 days)
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    technical = [
        c for c in corrections
        if c.get("correction_type") == "technical"
        and c.get("last_activated") and c["last_activated"] > cutoff
    ]

    to_show = (tendencies + technical)[-n:]

    if not to_show:
        return ""

    lines = ["Don't repeat these:"]
    for c in to_show:
        line = f"  - {c['mistake']} → {c['correction']}"
        if c.get("fails_when"):
            line += f" [fails when: {c['fails_when']}]"
        if c.get("fine_when"):
            line += f" [fine when: {c['fine_when']}]"
        lines.append(line)

    return "\n".join(lines)


def ensure_index() -> str:
    """Ensure ChromaDB index is in sync with JSON file. Call at boot.
    Returns status message. Fails LOUD if ChromaDB can't index corrections."""
    corrections = _load()
    if not corrections:
        return "No corrections to index."

    try:
        _sync_to_chroma(corrections)
        return f"Corrections indexed: {len(corrections)} entries."
    except Exception as e:
        msg = f"Corrections ChromaDB sync FAILED: {e}. Keyword search still works."
        logger.warning(msg)
        return msg
