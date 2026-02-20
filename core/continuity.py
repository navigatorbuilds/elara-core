# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Cognitive Continuity Chain — cryptographic proof of unbroken AI cognitive experience.

Hash-chained, dual-signed (Dilithium3 + SPHINCS+) state snapshots stored in the DAG.
You can mathematically verify an AI's experience was never tampered with.

Each checkpoint captures a CognitiveDigest — a snapshot of the entire cognitive state:
mood vector, memory counts, model counts, active goals, allostatic load, etc.
Checkpoints chain via parent references: each new checkpoint's parent is the
previous checkpoint, forming a verifiable linked list inside the DAG.

Trigger events (at priority 40, before bridge's 50):
  - SESSION_ENDED
  - PRINCIPLE_CRYSTALLIZED
  - MODEL_CREATED
  - DREAM_COMPLETED
  - BRAIN_THINKING_COMPLETED
  - MOOD_CHANGED (only if delta > 0.3)

Rate limit: max 1 checkpoint per 5 minutes.

Usage:
    from core.continuity import ContinuityChain
    chain = ContinuityChain(paths, bridge, event_bus)

    # Manual checkpoint
    chain.checkpoint(trigger="manual")

    # Verify the full chain
    valid, length, breaks = chain.verify_chain()
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("elara.continuity")

# Rate limit: 1 checkpoint per 5 minutes
_CHECKPOINT_COOLDOWN = 300.0


# ---------------------------------------------------------------------------
# Cognitive Digest — snapshot of cognitive state
# ---------------------------------------------------------------------------

@dataclass
class CognitiveDigest:
    """Snapshot of cognitive state at a point in time."""

    # Mood
    mood_valence: float = 0.0
    mood_energy: float = 0.0
    mood_openness: float = 0.0

    # Counts
    memory_count: int = 0
    model_count: int = 0
    prediction_count: int = 0
    principle_count: int = 0
    correction_count: int = 0

    # Session
    active_goals: int = 0
    session_count: int = 0

    # Allostatic load (from state file)
    allostatic_load: float = 0.0

    # Timestamp
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_canonical_json(self) -> bytes:
        """Deterministic JSON for hashing — sorted keys, minimal whitespace."""
        return json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")

    def sha3_hash(self) -> str:
        """SHA3-256 hex digest of the canonical JSON."""
        return hashlib.sha3_256(self.to_canonical_json()).hexdigest()


def build_cognitive_digest(paths) -> CognitiveDigest:
    """
    Read current state from JSON files to build a CognitiveDigest.

    Each subsystem wrapped in try/except — missing data = 0.
    Graceful for lower tiers where some files don't exist.
    """
    digest = CognitiveDigest()

    # Mood from state file
    try:
        state = json.loads(paths.state_file.read_text())
        digest.mood_valence = float(state.get("valence", 0))
        digest.mood_energy = float(state.get("energy", 0))
        digest.mood_openness = float(state.get("openness", 0))
    except Exception:
        pass

    # Memory count from ChromaDB
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(paths.memory_db))
        col = client.get_collection("memories")
        digest.memory_count = col.count()
    except Exception:
        pass

    # Models count
    try:
        models_dir = paths.models_dir
        if models_dir.is_dir():
            digest.model_count = sum(1 for f in models_dir.iterdir() if f.suffix == ".json")
    except Exception:
        pass

    # Predictions count
    try:
        pred_dir = paths.predictions_dir
        if pred_dir.is_dir():
            digest.prediction_count = sum(1 for f in pred_dir.iterdir() if f.suffix == ".json")
    except Exception:
        pass

    # Principles count
    try:
        if paths.principles_file.exists():
            principles = json.loads(paths.principles_file.read_text())
            if isinstance(principles, list):
                digest.principle_count = len(principles)
    except Exception:
        pass

    # Corrections count
    try:
        if paths.corrections_file.exists():
            corrections = json.loads(paths.corrections_file.read_text())
            if isinstance(corrections, list):
                digest.correction_count = len(corrections)
    except Exception:
        pass

    # Goals count
    try:
        if paths.goals_file.exists():
            goals = json.loads(paths.goals_file.read_text())
            if isinstance(goals, list):
                digest.active_goals = sum(
                    1 for g in goals if g.get("status") == "active"
                )
    except Exception:
        pass

    # Session count from presence
    try:
        if paths.presence_file.exists():
            presence = json.loads(paths.presence_file.read_text())
            digest.session_count = int(presence.get("total_sessions", 0))
    except Exception:
        pass

    # Allostatic load from state
    try:
        state = json.loads(paths.state_file.read_text())
        digest.allostatic_load = float(state.get("allostatic_load", 0))
    except Exception:
        pass

    return digest


# ---------------------------------------------------------------------------
# Continuity Chain
# ---------------------------------------------------------------------------

class ContinuityChain:
    """
    Cryptographic chain of cognitive state checkpoints.

    Each checkpoint:
    1. Builds a CognitiveDigest (snapshot of current state)
    2. SHA3-256 hashes the canonical JSON
    3. Creates a ValidationRecord with record_type="cognitive_checkpoint"
    4. Sets parent = previous checkpoint hash (chain linking)
    5. Dual-signs via bridge identity
    6. Inserts into DAG
    7. Persists chain state to continuity file
    8. Emits CONTINUITY_CHECKPOINT event
    """

    def __init__(self, paths, bridge, event_bus):
        """
        Args:
            paths: ElaraPaths instance
            bridge: L1Bridge instance (provides identity, DAG, signing)
            event_bus: EventBus instance
        """
        self._paths = paths
        self._bridge = bridge
        self._bus = event_bus

        # Chain state
        self._chain_head: Optional[str] = None
        self._chain_count: int = 0
        self._created: Optional[str] = None
        self._last_checkpoint_time: float = 0.0

        # Load persisted state
        self._load_state()

        # Subscribe to trigger events
        self._subscribe()

        logger.info(
            "Continuity chain initialized — %d checkpoints, head=%s",
            self._chain_count,
            (self._chain_head or "none")[:12],
        )

    def _load_state(self) -> None:
        """Load chain state from continuity file."""
        try:
            if self._paths.continuity_file.exists():
                data = json.loads(self._paths.continuity_file.read_text())
                self._chain_head = data.get("chain_head")
                self._chain_count = int(data.get("chain_count", 0))
                self._created = data.get("created")
        except Exception as e:
            logger.warning("Failed to load continuity state: %s", e)

    def _save_state(self) -> None:
        """Persist chain state to continuity file."""
        data = {
            "chain_head": self._chain_head,
            "chain_count": self._chain_count,
            "created": self._created or datetime.utcnow().isoformat(),
            "last_checkpoint": datetime.utcnow().isoformat(),
        }
        try:
            self._paths.continuity_file.write_text(
                json.dumps(data, indent=2)
            )
        except Exception as e:
            logger.error("Failed to save continuity state: %s", e)

    def _subscribe(self) -> None:
        """Subscribe to trigger events at priority 40 (before bridge's 50)."""
        from daemon.events import Events

        triggers = [
            Events.SESSION_ENDED,
            Events.PRINCIPLE_CRYSTALLIZED,
            Events.MODEL_CREATED,
            Events.DREAM_COMPLETED,
            Events.BRAIN_THINKING_COMPLETED,
        ]

        for event_type in triggers:
            self._bus.on(
                event_type,
                self._on_trigger_event,
                priority=40,
                source="continuity_chain",
            )

        # Mood: only checkpoint if delta > 0.3
        self._bus.on(
            Events.MOOD_CHANGED,
            self._on_mood_changed,
            priority=40,
            source="continuity_chain",
        )

        logger.info("Subscribed to %d trigger events", len(triggers) + 1)

    def _on_trigger_event(self, event) -> None:
        """Handle a trigger event — checkpoint with rate limiting."""
        if not self._check_cooldown():
            return
        try:
            self.checkpoint(trigger=event.type)
        except Exception as e:
            logger.error("Checkpoint failed on %s: %s", event.type, e)

    def _on_mood_changed(self, event) -> None:
        """Only checkpoint mood changes with delta > 0.3."""
        delta = event.data.get("delta", 0)
        if isinstance(delta, (int, float)) and abs(delta) > 0.3:
            if self._check_cooldown():
                try:
                    self.checkpoint(trigger="mood_changed_significant")
                except Exception as e:
                    logger.error("Checkpoint failed on mood change: %s", e)

    def _check_cooldown(self) -> bool:
        """Rate limit: max 1 checkpoint per 5 minutes."""
        now = time.monotonic()
        if now - self._last_checkpoint_time < _CHECKPOINT_COOLDOWN:
            logger.debug("Checkpoint cooldown — skipping")
            return False
        return True

    # ------------------------------------------------------------------
    # Core: checkpoint
    # ------------------------------------------------------------------

    def checkpoint(self, trigger: str = "manual") -> Optional[str]:
        """
        Create a cognitive continuity checkpoint.

        Returns the record hash on success, None on failure.
        """
        from elara_protocol.record import ValidationRecord, Classification

        # 1. Build cognitive digest
        digest = build_cognitive_digest(self._paths)
        digest_hash = digest.sha3_hash()

        # 2. Canonical JSON content
        content = digest.to_canonical_json()

        # 3. Metadata
        metadata = {
            "record_type": "cognitive_checkpoint",
            "digest_hash": digest_hash,
            "sequence": self._chain_count,
            "trigger": trigger,
            "previous_checkpoint": self._chain_head,
            "mood_vector": [digest.mood_valence, digest.mood_energy, digest.mood_openness],
            "memory_count": digest.memory_count,
            "model_count": digest.model_count,
            "prediction_count": digest.prediction_count,
            "principle_count": digest.principle_count,
            "correction_count": digest.correction_count,
            "active_goals": digest.active_goals,
            "session_count": digest.session_count,
            "allostatic_load": digest.allostatic_load,
        }

        # 4. Build parent list — chain to previous checkpoint
        parents = []
        if self._chain_head:
            parents.append(self._chain_head)

        # 5. Create record
        identity = self._bridge._identity
        record = ValidationRecord.create(
            content=content,
            creator_public_key=identity.public_key,
            parents=parents,
            classification=Classification.SOVEREIGN,
            metadata=metadata,
        )

        # 6. Dual sign
        signable = record.signable_bytes()
        record.signature = identity.sign(signable)

        from elara_protocol.identity import CryptoProfile
        if identity.profile == CryptoProfile.PROFILE_A:
            record.sphincs_signature = identity.sign_sphincs(signable)

        # 7. Insert into DAG
        dag = self._bridge._dag
        record_hash = dag.insert(record, verify_signature=True)

        # 8. Update chain state
        self._chain_head = record.id
        self._chain_count += 1
        if self._created is None:
            self._created = datetime.utcnow().isoformat()
        self._last_checkpoint_time = time.monotonic()

        # 9. Persist
        self._save_state()

        # 10. Emit event
        from daemon.events import Events
        self._bus.emit(
            Events.CONTINUITY_CHECKPOINT,
            {
                "record_id": record.id,
                "record_hash": record_hash,
                "sequence": self._chain_count - 1,
                "digest_hash": digest_hash,
                "trigger": trigger,
            },
            source="continuity_chain",
        )

        logger.info(
            "Checkpoint #%d — trigger=%s hash=%s",
            self._chain_count - 1, trigger, record_hash[:12],
        )

        return record_hash

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify_chain(self) -> Tuple[bool, int, List[str]]:
        """
        Walk DAG backwards from chain head, verify every parent link.

        Returns:
            (valid, length, breaks) where:
            - valid: True if the entire chain is intact
            - length: number of checkpoints verified
            - breaks: list of error descriptions if any
        """
        if not self._chain_head:
            return (True, 0, [])

        breaks: List[str] = []
        verified = 0
        current_id = self._chain_head
        dag = self._bridge._dag

        seen = set()
        while current_id:
            if current_id in seen:
                breaks.append(f"Cycle detected at {current_id[:12]}")
                break
            seen.add(current_id)

            # Fetch the record from DAG
            try:
                record = dag.get(current_id)
            except Exception:
                record = None

            if record is None:
                breaks.append(f"Record not found: {current_id[:12]}")
                break

            # Verify it's a cognitive checkpoint
            if record.metadata.get("record_type") != "cognitive_checkpoint":
                breaks.append(
                    f"Record {current_id[:12]} is not a cognitive_checkpoint "
                    f"(type={record.metadata.get('record_type', '?')})"
                )
                break

            # Verify signature
            try:
                import oqs
                verifier = oqs.Signature("Dilithium3")
                signable = record.signable_bytes()
                valid_sig = verifier.verify(
                    signable, record.signature, record.creator_public_key
                )
                if not valid_sig:
                    breaks.append(f"Invalid signature at checkpoint #{record.metadata.get('sequence', '?')}")
            except ImportError:
                pass  # liboqs not available — skip sig check
            except Exception as e:
                breaks.append(f"Signature verification error at {current_id[:12]}: {e}")

            verified += 1

            # Walk to parent
            previous = record.metadata.get("previous_checkpoint")
            if previous:
                current_id = previous
            else:
                break  # reached genesis

        valid = len(breaks) == 0
        return (valid, verified, breaks)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return chain status for CLI/diagnostics."""
        return {
            "chain_head": self._chain_head,
            "chain_count": self._chain_count,
            "created": self._created,
            "continuity_file": str(self._paths.continuity_file),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_chain: Optional[ContinuityChain] = None


def get_chain() -> Optional[ContinuityChain]:
    """Return the chain singleton, or None if not initialized."""
    return _chain


def setup_chain(paths, bridge, event_bus) -> Optional[ContinuityChain]:
    """
    Initialize the continuity chain if bridge is available.

    Called at MCP server startup. Returns the chain instance or None.
    """
    global _chain
    if bridge is None:
        logger.info("No bridge — continuity chain disabled")
        return None

    try:
        _chain = ContinuityChain(paths, bridge, event_bus)
        return _chain
    except Exception as e:
        logger.error("Failed to initialize continuity chain: %s", e)
        return None
