"""
Elara Conversation Memory — Core base class.

Database init, manifest management, text extraction utilities, stats.
"""

import json
import logging
import os
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger("elara.memory.conversations")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from core.paths import get_paths

_p = get_paths()
CONVERSATIONS_DIR = _p.conversations_db
MANIFEST_PATH = CONVERSATIONS_DIR / "ingested.json"
PROJECTS_DIR = _p.claude_projects
EPISODES_DIR = _p.episodes_dir
EPISODES_INDEX = EPISODES_DIR / "index.json"

# Current schema version — bump to force re-index on upgrade
SCHEMA_VERSION = 2

# Regex to strip <system-reminder>...</system-reminder> blocks
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)

# Recency scoring parameters
RECENCY_HALF_LIFE_DAYS = 30  # After 30 days, recency factor = 0.5
RECENCY_WEIGHT = 0.15  # 15% of final score comes from recency


class ConversationBase:
    """Base class with DB init, manifest, and text utilities."""

    def __init__(self):
        self.client = None
        self.collection = None

        if CHROMA_AVAILABLE:
            self._init_db()

    def _init_db(self):
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(CONVERSATIONS_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name="elara_conversations_v2",
            metadata={
                "description": "Elara's conversation memory — cosine similarity",
                "hnsw:space": "cosine",
            }
        )

    def _load_manifest(self) -> Dict[str, Any]:
        if not MANIFEST_PATH.exists():
            return {}
        try:
            with open(MANIFEST_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Manifest is not a dict, resetting")
                return {}
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt manifest, resetting: %s", e)
            return {}

    def _save_manifest(self, manifest: Dict[str, Any]):
        manifest["_schema_version"] = SCHEMA_VERSION
        with open(MANIFEST_PATH, 'w') as f:
            json.dump(manifest, f, indent=2)

    def _generate_id(self, session_id: str, exchange_index: int, timestamp: str) -> str:
        content = f"{session_id}:{exchange_index}:{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _clean_text(self, text: str) -> str:
        """Strip system-reminder blocks and clean up text."""
        text = SYSTEM_REMINDER_RE.sub('', text)
        text = text.strip()
        return text

    def _extract_user_text(self, message: dict) -> Optional[str]:
        """Extract user text from a message entry. Returns None if not real user input."""
        content = message.get("message", {}).get("content", "")

        if isinstance(content, str):
            text = self._clean_text(content)
            if text:
                return text
            return None
        elif isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned:
                        texts.append(cleaned)
            if texts:
                return "\n".join(texts)
        return None

    def _extract_assistant_text(self, message: dict) -> Optional[str]:
        """Extract assistant text from a message entry. Skip tool_use, thinking blocks."""
        content = message.get("message", {}).get("content", [])

        if isinstance(content, str):
            text = self._clean_text(content)
            return text if text else None

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned:
                        texts.append(cleaned)
            if texts:
                return "\n".join(texts)
        return None

    def count(self) -> int:
        if not self.collection:
            return 0
        return self.collection.count()

    def stats(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        sessions = set()
        total_exchanges = 0
        for key, info in manifest.items():
            if key.startswith("_"):
                continue
            sessions.add(info.get("session_id", ""))
            total_exchanges += info.get("exchanges_ingested", 0)

        # Count cross-referenced exchanges
        cross_ref_count = 0
        if self.collection:
            try:
                sample = self.collection.get(include=["metadatas"], limit=1000)
                if sample["metadatas"]:
                    cross_ref_count = sum(
                        1 for m in sample["metadatas"] if m.get("episode_id")
                    )
            except Exception:
                pass

        return {
            "indexed_exchanges": self.count(),
            "sessions_ingested": len(sessions),
            "manifest_entries": len([k for k in manifest if not k.startswith("_")]),
            "total_exchanges_from_manifest": total_exchanges,
            "cross_referenced": cross_ref_count,
            "schema_version": manifest.get("_schema_version", 1),
        }
