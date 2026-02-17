# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Workflows — Learned action sequences from episode history.

Storage: ~/.elara/elara-workflows/{workflow_id}.json (individual files)
Index:   ~/.elara/elara-workflows-db/ (ChromaDB, cosine similarity)

Workflows are proactive: when the current task matches the trigger of a
known workflow, remaining steps are surfaced as suggestions.

The overnight brain detects recurring sequences from episodes and
crystallizes them into workflow patterns. Confidence rises with
confirmation, drops with skips.
"""

import json
import hashlib
import logging
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
from daemon.events import bus, Events
from daemon.schemas import (
    WorkflowPattern, WorkflowStep,
    ElaraNotFoundError,
)

logger = logging.getLogger("elara.workflows")

_p = get_paths()
WORKFLOWS_DIR = _p.workflows_dir
WORKFLOWS_DB_DIR = _p.workflows_db

# Confidence mechanics
CONFIRM_DELTA = 0.05
WEAKEN_DELTA = -0.08
SKIP_DELTA = -0.03
MAX_CONFIDENCE = 0.95
RETIRE_THRESHOLD = 0.15


# ============================================================================
# Storage layer (individual JSON files — source of truth)
# ============================================================================

def _workflow_path(workflow_id: str) -> Path:
    return WORKFLOWS_DIR / f"{workflow_id}.json"


def _load_workflow(workflow_id: str) -> Optional[Dict]:
    path = _workflow_path(workflow_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return WorkflowPattern.model_validate(data).model_dump()
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to load workflow %s: %s", workflow_id, e)
        return None


def _save_workflow(workflow: Dict):
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    model = WorkflowPattern.model_validate(workflow)
    path = _workflow_path(workflow["workflow_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(model.model_dump_json(indent=2))
    import os
    fd = os.open(str(tmp), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(str(tmp), str(path))


def _load_all() -> List[Dict]:
    if not WORKFLOWS_DIR.exists():
        return []
    workflows = []
    for f in sorted(WORKFLOWS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            workflows.append(WorkflowPattern.model_validate(data).model_dump())
        except (json.JSONDecodeError, Exception):
            pass
    return workflows


def _generate_id(name: str) -> str:
    raw = f"{name}:{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ============================================================================
# ChromaDB index (semantic search for activation)
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
        WORKFLOWS_DB_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(WORKFLOWS_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_collection = _chroma_client.get_or_create_collection(
            name="elara_workflows",
            metadata={"hnsw:space": "cosine"},
        )
        return _chroma_collection
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to init workflows ChromaDB: %s", e)
        return None


def _build_document(workflow: Dict) -> str:
    """Build the text document for ChromaDB embedding."""
    name = workflow.get("name", "")
    trigger = workflow.get("trigger", "")
    steps_text = ", ".join(
        s.get("action", "") for s in workflow.get("steps", [])
    )
    return f"{name}. Trigger: {trigger}. Steps: {steps_text}"


def _index_workflow(workflow: Dict):
    collection = _get_collection()
    if not collection:
        return

    text = _build_document(workflow)
    if not text.strip():
        return

    metadata = {
        "domain": workflow.get("domain", "development"),
        "status": workflow.get("status", "active"),
        "confidence": workflow.get("confidence", 0.5),
        "created": workflow.get("created", ""),
        "times_matched": workflow.get("times_matched", 0),
    }

    try:
        collection.upsert(
            ids=[workflow["workflow_id"]],
            documents=[text],
            metadatas=[metadata],
        )
    except Exception as e:
        logger.warning("Failed to index workflow %s: %s", workflow.get("workflow_id", "?"), e)


# ============================================================================
# Core operations
# ============================================================================

def create_workflow(
    name: str,
    domain: str = "development",
    trigger: str = "",
    steps: Optional[List[Dict]] = None,
    confidence: float = 0.5,
    source_episodes: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Dict:
    """Create a new workflow pattern."""
    logger.info("Creating workflow [%s]: %s", domain, name[:80])

    workflow_id = _generate_id(name)
    now = datetime.now().isoformat()

    step_models = []
    for s in (steps or []):
        if isinstance(s, dict):
            step_models.append(WorkflowStep.model_validate(s).model_dump())
        else:
            step_models.append(s)

    workflow = WorkflowPattern(
        workflow_id=workflow_id,
        name=name,
        domain=domain,
        trigger=trigger,
        steps=step_models,
        confidence=min(round(confidence, 2), MAX_CONFIDENCE),
        source_episodes=source_episodes or [],
        times_matched=0,
        times_completed=0,
        times_skipped=0,
        status="active",
        created=now,
        last_matched=None,
        tags=tags or [],
    ).model_dump()

    _save_workflow(workflow)
    _index_workflow(workflow)

    bus.emit(Events.WORKFLOW_CREATED, {
        "workflow_id": workflow_id,
        "name": name[:200],
        "domain": domain,
        "steps": len(step_models),
    }, source="workflows")

    return workflow


def get_workflow(workflow_id: str) -> Optional[Dict]:
    """Get a single workflow by ID."""
    return _load_workflow(workflow_id)


def list_workflows(
    status: Optional[str] = None,
    domain: Optional[str] = None,
) -> List[Dict]:
    """List all workflows, optionally filtered."""
    workflows = _load_all()
    if status:
        workflows = [w for w in workflows if w.get("status") == status]
    if domain:
        workflows = [w for w in workflows if w.get("domain") == domain]
    workflows.sort(key=lambda w: w.get("confidence", 0), reverse=True)
    return workflows


def search_workflows(query: str, n: int = 5) -> List[Dict]:
    """Semantic search across workflows."""
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

        for i, wid in enumerate(ids):
            workflow = _load_workflow(wid)
            if workflow:
                similarity = 1.0 - distances[i] if i < len(distances) else 0.0
                workflow["_similarity"] = round(similarity, 3)
                found.append(workflow)

        return found
    except Exception as e:
        logger.warning("ChromaDB workflow search failed: %s", e)
        return _keyword_search(query, n)


def check_workflows(task_context: str, n: int = 3) -> List[Dict]:
    """
    Activation function — find workflows matching current task context.

    Like corrections.check_corrections but for proactive workflow surfacing.
    Only returns active workflows above a similarity threshold.
    """
    collection = _get_collection()
    if not collection:
        return []

    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[task_context],
            n_results=min(n, count),
            where={"status": "active"},
        )

        found = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, wid in enumerate(ids):
            similarity = 1.0 - distances[i] if i < len(distances) else 0.0
            if similarity < 0.45:
                continue
            workflow = _load_workflow(wid)
            if workflow and workflow.get("status") == "active":
                workflow["_similarity"] = round(similarity, 3)
                found.append(workflow)

        return found
    except Exception as e:
        logger.warning("Workflow check failed: %s", e)
        return []


def record_match(workflow_id: str) -> None:
    """Record that a workflow was matched (surfaced to user)."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["times_matched"] = workflow.get("times_matched", 0) + 1
    workflow["last_matched"] = datetime.now().isoformat()
    _save_workflow(workflow)
    _index_workflow(workflow)

    bus.emit(Events.WORKFLOW_MATCHED, {
        "workflow_id": workflow_id,
        "times_matched": workflow["times_matched"],
    }, source="workflows")


def record_completion(workflow_id: str) -> None:
    """Record that a workflow was completed (all steps done)."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["times_completed"] = workflow.get("times_completed", 0) + 1
    workflow["confidence"] = min(MAX_CONFIDENCE, round(
        workflow.get("confidence", 0.5) + CONFIRM_DELTA, 2))
    _save_workflow(workflow)
    _index_workflow(workflow)

    bus.emit(Events.WORKFLOW_COMPLETED, {
        "workflow_id": workflow_id,
        "times_completed": workflow["times_completed"],
        "confidence": workflow["confidence"],
    }, source="workflows")


def record_skip(workflow_id: str) -> None:
    """Record that a workflow was skipped (user didn't follow it)."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["times_skipped"] = workflow.get("times_skipped", 0) + 1
    workflow["confidence"] = max(0.0, round(
        workflow.get("confidence", 0.5) + SKIP_DELTA, 2))

    if workflow["confidence"] < RETIRE_THRESHOLD:
        workflow["status"] = "retired"

    _save_workflow(workflow)
    _index_workflow(workflow)


def confirm_workflow(workflow_id: str, episode_id: Optional[str] = None) -> None:
    """Confirm a workflow — overnight brain saw it in another episode."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["confidence"] = min(MAX_CONFIDENCE, round(
        workflow.get("confidence", 0.5) + CONFIRM_DELTA, 2))

    if episode_id and episode_id not in workflow.get("source_episodes", []):
        workflow["source_episodes"].append(episode_id)

    _save_workflow(workflow)
    _index_workflow(workflow)


def weaken_workflow(workflow_id: str, reason: Optional[str] = None) -> None:
    """Weaken a workflow — contradicting evidence."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["confidence"] = max(0.0, round(
        workflow.get("confidence", 0.5) + WEAKEN_DELTA, 2))

    if workflow["confidence"] < RETIRE_THRESHOLD:
        workflow["status"] = "retired"

    _save_workflow(workflow)
    _index_workflow(workflow)


def retire_workflow(workflow_id: str) -> None:
    """Retire a workflow — no longer relevant."""
    workflow = _load_workflow(workflow_id)
    if not workflow:
        raise ElaraNotFoundError(f"Workflow {workflow_id} not found.")

    workflow["status"] = "retired"
    _save_workflow(workflow)
    _index_workflow(workflow)

    bus.emit(Events.WORKFLOW_RETIRED, {
        "workflow_id": workflow_id,
        "name": workflow.get("name", ""),
    }, source="workflows")


def get_workflow_stats() -> Dict:
    """Aggregate stats across all workflows."""
    workflows = _load_all()
    if not workflows:
        return {
            "total": 0,
            "by_status": {},
            "by_domain": {},
            "avg_confidence": None,
            "total_matches": 0,
            "total_completions": 0,
            "total_skips": 0,
        }

    by_status = {}
    by_domain = {}
    confidences = []
    total_matched = 0
    total_completed = 0
    total_skipped = 0

    for w in workflows:
        s = w.get("status", "active")
        by_status[s] = by_status.get(s, 0) + 1

        d = w.get("domain", "development")
        by_domain[d] = by_domain.get(d, 0) + 1

        if s == "active":
            confidences.append(w.get("confidence", 0.5))

        total_matched += w.get("times_matched", 0)
        total_completed += w.get("times_completed", 0)
        total_skipped += w.get("times_skipped", 0)

    return {
        "total": len(workflows),
        "by_status": by_status,
        "by_domain": by_domain,
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "total_matches": total_matched,
        "total_completions": total_completed,
        "total_skips": total_skipped,
    }


def reindex_all() -> Dict:
    """Rebuild ChromaDB index from JSON files."""
    workflows = _load_all()
    for w in workflows:
        _index_workflow(w)
    return {"indexed": len(workflows)}


# ============================================================================
# Keyword fallback
# ============================================================================

def _keyword_search(query: str, n: int) -> List[Dict]:
    query_words = set(query.lower().split())
    workflows = _load_all()
    scored = []
    for w in workflows:
        text = f"{w.get('name','')} {w.get('trigger','')} {w.get('domain','')} {' '.join(w.get('tags',[]))}".lower()
        for s in w.get("steps", []):
            text += f" {s.get('action', '')}"
        overlap = len(query_words & set(text.split()))
        if overlap > 0:
            scored.append((overlap, w))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [w for _, w in scored[:n]]
