# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Unified Decision Registry (UDR) — crystallized judgments that prevent repetition.

Storage: ~/.elara/elara-udr.db (SQLite, WAL mode)
In-memory: Python set of rejected action_signatures for O(1) hook checks

The UDR solves a fundamental problem: across 110+ sessions, Elara repeatedly
suggests things already tried and failed (arXiv 5x, ESA, TechRxiv, etc.).
14 memory systems store observations but never crystallize verdicts.

Architecture:
  WRITE-TIME: corrections/outcomes/manual → DecisionRegistry (SQLite)
  BOOT-TIME:  Load rejected entity set into memory (Python set, O(1))
  HOOK-TIME:  Keyword scan prompt → entity set → [DECISION-CHECK] injection

Design decisions:
  - SQLite over JSON/ChromaDB: need indexed lookups by signature, exact match
  - Python set over bloom filter: <1000 decisions, O(1), simpler, swappable
  - Upsert semantics: same domain:entity bumps confidence +0.1, no duplicates
  - Fail-silent feeds: UDR failure never breaks corrections or outcomes
"""

import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from core.paths import get_paths

logger = logging.getLogger("elara.udr")


# ============================================================================
# Schema
# ============================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    action_signature TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    entity TEXT NOT NULL,
    verdict TEXT NOT NULL DEFAULT 'rejected',
    reason TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.8,
    source TEXT NOT NULL DEFAULT 'manual',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    session INTEGER,
    tags TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_decisions_domain ON decisions(domain);
CREATE INDEX IF NOT EXISTS idx_decisions_entity ON decisions(entity);
CREATE INDEX IF NOT EXISTS idx_decisions_verdict ON decisions(verdict);
"""


# ============================================================================
# DecisionRegistry
# ============================================================================

class DecisionRegistry:
    """
    SQLite-backed decision ledger with in-memory fast-check set.

    Follows KnowledgeStore pattern: lazy connection, WAL mode, row_factory.
    """

    def __init__(self):
        self._p = get_paths()
        self._conn: Optional[sqlite3.Connection] = None
        self._entity_set: Set[str] = set()  # rejected signatures for O(1) check
        self._booted = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        db_path = self._p.udr_file
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize to lowercase, strip whitespace."""
        return text.strip().lower().replace(" ", "_")

    @staticmethod
    def _signature(domain: str, entity: str) -> str:
        """Build action_signature from domain:entity."""
        return f"{DecisionRegistry._normalize(domain)}:{DecisionRegistry._normalize(entity)}"

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def record_decision(
        self,
        domain: str,
        entity: str,
        verdict: str = "rejected",
        reason: str = "",
        confidence: float = 0.8,
        source: str = "manual",
        session: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """
        Record or upsert a decision.

        Upsert semantics: if same domain:entity exists, bump confidence +0.1
        and update reason/source/timestamp.
        """
        domain_n = self._normalize(domain)
        entity_n = self._normalize(entity)
        sig = self._signature(domain, entity)
        now = datetime.now().isoformat()
        tags_str = ",".join(tags) if tags else ""

        db = self._db()

        # Check for existing
        row = db.execute(
            "SELECT * FROM decisions WHERE action_signature = ?", (sig,)
        ).fetchone()

        if row:
            # Upsert: bump confidence, update fields
            new_conf = min(1.0, row["confidence"] + 0.1)
            db.execute(
                """UPDATE decisions
                   SET verdict = ?, reason = ?, confidence = ?,
                       source = ?, updated = ?, session = ?, tags = ?
                   WHERE action_signature = ?""",
                (verdict, reason, round(new_conf, 2), source, now,
                 session, tags_str, sig),
            )
            db.commit()
            result = self._row_to_dict(db.execute(
                "SELECT * FROM decisions WHERE action_signature = ?", (sig,)
            ).fetchone())
            logger.info("UDR upsert: %s (confidence %.2f -> %.2f)",
                        sig, row["confidence"], new_conf)
        else:
            # Insert new
            db.execute(
                """INSERT INTO decisions
                   (action_signature, domain, entity, verdict, reason,
                    confidence, source, created, updated, session, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sig, domain_n, entity_n, verdict, reason,
                 round(confidence, 2), source, now, now, session, tags_str),
            )
            db.commit()
            result = self._row_to_dict(db.execute(
                "SELECT * FROM decisions WHERE action_signature = ?", (sig,)
            ).fetchone())
            logger.info("UDR recorded: %s [%s] (conf=%.2f)",
                        sig, verdict, confidence)

        # Update in-memory set
        if verdict in ("rejected", "failed"):
            self._entity_set.add(sig)
        else:
            self._entity_set.discard(sig)

        # Emit event (lazy import to avoid circular deps at module level)
        try:
            from daemon.events import bus, Events
            bus.emit(Events.DECISION_RECORDED, {
                "signature": sig,
                "domain": domain_n,
                "entity": entity_n,
                "verdict": verdict,
            }, source="udr")
        except Exception:
            pass

        return result

    def check_decision(self, domain: str, entity: str) -> Optional[Dict]:
        """Check if a decision exists for this domain:entity pair."""
        sig = self._signature(domain, entity)
        db = self._db()
        row = db.execute(
            "SELECT * FROM decisions WHERE action_signature = ?", (sig,)
        ).fetchone()

        if row:
            try:
                from daemon.events import bus, Events
                bus.emit(Events.DECISION_CHECKED, {
                    "signature": sig,
                    "verdict": row["verdict"],
                }, source="udr")
            except Exception:
                pass
            return self._row_to_dict(row)
        return None

    def quick_check(self, domain: str, entity: str) -> bool:
        """O(1) check against in-memory rejected set. No DB hit."""
        sig = self._signature(domain, entity)
        return sig in self._entity_set

    def check_entities(self, text: str) -> List[Dict]:
        """
        Scan text for any entity keywords in the rejected set.
        Returns matching decisions. Used by the intention hook.

        Zero LLM calls — pure keyword matching against entity names.
        """
        if not self._entity_set:
            self._load_entity_set()

        text_lower = text.lower()
        matches = []

        # Build entity lookup: entity_name → list of signatures
        db = self._db()
        rows = db.execute(
            "SELECT * FROM decisions WHERE verdict IN ('rejected', 'failed')"
        ).fetchall()

        for row in rows:
            entity = row["entity"]
            # Skip very short entities to reduce false positives
            if len(entity) < 3:
                continue
            # Match entity as-is OR with underscores as spaces
            # (entities stored as "tokenomics_whitepaper" should match
            #  "tokenomics whitepaper" in natural text)
            entity_spaced = entity.replace("_", " ")
            if entity in text_lower or entity_spaced in text_lower:
                matches.append(self._row_to_dict(row))

        return matches[:2]  # Max 2 hits per hook principle

    def list_decisions(
        self,
        domain: Optional[str] = None,
        verdict: Optional[str] = None,
        n: int = 20,
    ) -> List[Dict]:
        """List decisions, optionally filtered by domain or verdict."""
        db = self._db()
        query = "SELECT * FROM decisions"
        params: list = []
        conditions = []

        if domain:
            conditions.append("domain = ?")
            params.append(self._normalize(domain))
        if verdict:
            conditions.append("verdict = ?")
            params.append(verdict.lower())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated DESC LIMIT ?"
        params.append(n)

        rows = db.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def review_decision(self, domain: str, entity: str) -> Optional[Dict]:
        """Get full details for a single decision. Alias for check_decision."""
        return self.check_decision(domain, entity)

    def stats(self) -> Dict:
        """Aggregate statistics."""
        db = self._db()

        total = db.execute("SELECT COUNT(*) as c FROM decisions").fetchone()["c"]
        by_verdict = {}
        for row in db.execute(
            "SELECT verdict, COUNT(*) as c FROM decisions GROUP BY verdict"
        ).fetchall():
            by_verdict[row["verdict"]] = row["c"]

        by_domain = {}
        for row in db.execute(
            "SELECT domain, COUNT(*) as c FROM decisions GROUP BY domain ORDER BY c DESC"
        ).fetchall():
            by_domain[row["domain"]] = row["c"]

        by_source = {}
        for row in db.execute(
            "SELECT source, COUNT(*) as c FROM decisions GROUP BY source ORDER BY c DESC"
        ).fetchall():
            by_source[row["source"]] = row["c"]

        avg_conf = db.execute(
            "SELECT AVG(confidence) as a FROM decisions"
        ).fetchone()["a"]

        return {
            "total_decisions": total,
            "by_verdict": by_verdict,
            "by_domain": by_domain,
            "by_source": by_source,
            "avg_confidence": round(avg_conf, 3) if avg_conf else 0,
            "entity_set_size": len(self._entity_set),
        }

    def boot_decisions(self) -> str:
        """
        Boot-time loader: populate in-memory entity set and return summary.
        Called at session start for instant hook checks.
        """
        self._load_entity_set()
        self._booted = True

        if not self._entity_set:
            return "UDR: No rejected decisions loaded."

        # Get a sample of recent rejections for boot display
        db = self._db()
        recent = db.execute(
            """SELECT domain, entity, reason FROM decisions
               WHERE verdict IN ('rejected', 'failed')
               ORDER BY updated DESC LIMIT 5"""
        ).fetchall()

        lines = [f"UDR: {len(self._entity_set)} blocked entities loaded."]
        for r in recent:
            lines.append(f"  - {r['domain']}:{r['entity']} — {r['reason'][:60]}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Backfill from existing systems
    # ------------------------------------------------------------------

    def backfill_from_corrections(self) -> int:
        """
        Scan existing corrections and extract permanent rejections.
        Returns number of decisions created.
        """
        count = 0
        try:
            from daemon.corrections import list_corrections
            corrections = list_corrections(n=50)

            for c in corrections:
                # Extract entity from correction text using heuristics
                domain, entity = self._extract_from_correction(c)
                if domain and entity:
                    self.record_decision(
                        domain=domain,
                        entity=entity,
                        verdict="rejected",
                        reason=c.get("correction", "")[:200],
                        confidence=0.9,
                        source="backfill_correction",
                    )
                    count += 1
        except Exception as e:
            logger.warning("Backfill from corrections failed: %s", e)

        logger.info("Backfilled %d decisions from corrections", count)
        return count

    def backfill_from_outcomes(self) -> int:
        """
        Scan existing outcomes and extract losses as failed decisions.
        Returns number of decisions created.
        """
        count = 0
        try:
            from daemon.outcomes import list_outcomes
            outcomes = list_outcomes(assessment="loss", n=50)

            for o in outcomes:
                domain, entity = self._extract_from_outcome(o)
                if domain and entity:
                    self.record_decision(
                        domain=domain,
                        entity=entity,
                        verdict="failed",
                        reason=o.get("lesson", o.get("actual", ""))[:200],
                        confidence=0.8,
                        source="backfill_outcome",
                    )
                    count += 1
        except Exception as e:
            logger.warning("Backfill from outcomes failed: %s", e)

        logger.info("Backfilled %d decisions from outcomes", count)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_entity_set(self):
        """Load all rejected/failed signatures into memory."""
        db = self._db()
        rows = db.execute(
            "SELECT action_signature FROM decisions WHERE verdict IN ('rejected', 'failed')"
        ).fetchall()
        self._entity_set = {r["action_signature"] for r in rows}
        logger.debug("Entity set loaded: %d entries", len(self._entity_set))

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict:
        """Convert a sqlite3.Row to a regular dict."""
        d = dict(row)
        # Convert tags back to list
        tags_str = d.get("tags", "")
        d["tags"] = [t for t in tags_str.split(",") if t] if tags_str else []
        return d

    @staticmethod
    def _extract_from_correction(correction: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract domain:entity from a correction.
        Returns (None, None) if can't determine.
        """
        text = f"{correction.get('mistake', '')} {correction.get('correction', '')}".lower()

        # Known patterns — expand over time
        patterns = {
            ("upload", "arxiv"): ["arxiv", "arx iv"],
            ("upload", "techrxiv"): ["techrxiv"],
            ("outreach", "professors"): ["professor outreach", "professor email"],
            ("outreach", "esa"): ["esa", "european space agency"],
            ("upload", "hardware_whitepaper"): ["hardware whitepaper", "hardware paper"],
            ("upload", "tokenomics_whitepaper"): ["tokenomics whitepaper", "tokenomics paper"],
            ("promotion", "self_promotion"): ["self-promotion", "self promotion"],
            ("application", "grants"): ["grant application", "grant proposal"],
        }

        for (domain, entity), keywords in patterns.items():
            for kw in keywords:
                if kw in text:
                    return domain, entity

        return None, None

    @staticmethod
    def _extract_from_outcome(outcome: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract domain:entity from a failed outcome.
        Returns (None, None) if can't determine.
        """
        text = f"{outcome.get('decision', '')} {outcome.get('context', '')}".lower()
        tags = outcome.get("tags", [])

        # Use tags if available
        if tags and len(tags) >= 2:
            return tags[0], tags[1]

        # Known patterns
        for keyword, (domain, entity) in {
            "arxiv": ("upload", "arxiv"),
            "techrxiv": ("upload", "techrxiv"),
        }.items():
            if keyword in text:
                return domain, entity

        return None, None


# ============================================================================
# Singleton
# ============================================================================

_instance: Optional[DecisionRegistry] = None


def get_registry() -> DecisionRegistry:
    """Return the global DecisionRegistry singleton (lazy-init)."""
    global _instance
    if _instance is None:
        _instance = DecisionRegistry()
    return _instance


def reset_registry():
    """Reset singleton. For testing."""
    global _instance
    if _instance is not None:
        _instance.close()
    _instance = None
