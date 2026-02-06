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

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

CORRECTIONS_FILE = Path.home() / ".claude" / "elara-corrections.json"
CORRECTIONS_DB_DIR = Path.home() / ".claude" / "elara-corrections-db"
MAX_CORRECTIONS = 50


# ============================================================================
# Storage layer (JSON file — source of truth)
# ============================================================================

def _load() -> List[Dict]:
    if not CORRECTIONS_FILE.exists():
        return []
    with open(CORRECTIONS_FILE, "r") as f:
        return json.load(f)


def _save(corrections: List[Dict]):
    CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CORRECTIONS_FILE, "w") as f:
        json.dump(corrections, f, indent=2)


def _ensure_v2_fields(entry: Dict) -> Dict:
    """Ensure a correction has all v2 fields. Non-destructive."""
    defaults = {
        "correction_type": "tendency",
        "fails_when": None,
        "fine_when": None,
        "last_activated": None,
        "times_surfaced": 0,
        "times_dismissed": 0,
    }
    for key, default in defaults.items():
        if key not in entry:
            entry[key] = default
    return entry


def _migrate_if_needed(corrections: List[Dict]) -> bool:
    """Migrate v1 corrections to v2 schema. Returns True if any changed."""
    changed = False
    for entry in corrections:
        before = set(entry.keys())
        _ensure_v2_fields(entry)
        if set(entry.keys()) != before:
            changed = True
    return changed


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

    ids = []
    documents = []
    metadatas = []

    for entry in corrections:
        entry = _ensure_v2_fields(entry)
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
    corrections = _load()

    # Migrate existing entries if needed
    if _migrate_if_needed(corrections):
        _save(corrections)

    entry = {
        "id": len(corrections) + 1,
        "mistake": mistake,
        "correction": correction,
        "context": context,
        "correction_type": correction_type,
        "fails_when": fails_when,
        "fine_when": fine_when,
        "date": datetime.now().isoformat(),
        "last_activated": None,
        "times_surfaced": 0,
        "times_dismissed": 0,
    }
    corrections.append(entry)

    # Cap at MAX_CORRECTIONS, remove oldest
    if len(corrections) > MAX_CORRECTIONS:
        corrections = corrections[-MAX_CORRECTIONS:]

    _save(corrections)

    # Index in ChromaDB
    _sync_to_chroma([entry])

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


def check_corrections(task_description: str, n_results: int = 3) -> List[Dict]:
    """
    Semantic search: find corrections relevant to current task context.

    This is the activation function — it finds corrections that MATCH
    what you're about to do, not just keyword overlap.

    Returns corrections with their conditions (fails_when/fine_when)
    so the caller can decide whether to heed the warning.
    """
    collection = _get_collection()

    if not collection or collection.count() == 0:
        # Fall back to keyword search
        return search_corrections(task_description)

    # Ensure index is current
    corrections = _load()
    _sync_to_chroma(corrections)

    results = collection.query(
        query_texts=[task_description],
        n_results=min(n_results, collection.count()),
    )

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
                full_entry = _ensure_v2_fields(c.copy())
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
    _migrate_if_needed(corrections)

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
    _migrate_if_needed(corrections)

    dormant = []
    cutoff = datetime.now() - timedelta(days=days)

    for entry in corrections:
        entry = _ensure_v2_fields(entry)
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
    _migrate_if_needed(corrections)

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


def ensure_index():
    """Ensure ChromaDB index is in sync with JSON file. Call at boot."""
    corrections = _load()
    if corrections:
        if _migrate_if_needed(corrections):
            _save(corrections)
        _sync_to_chroma(corrections)
