# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Episodic memory core — init, ChromaDB, index management, helpers.
"""

import json
from pathlib import Path
from typing import Optional

from daemon.schemas import atomic_write_json

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from daemon.state import get_mood
    STATE_AVAILABLE = True
except ImportError:
    STATE_AVAILABLE = False

try:
    from daemon import llm
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

from core.paths import get_paths

_p = get_paths()
EPISODES_DIR = _p.episodes_dir
EPISODES_INDEX = EPISODES_DIR / "index.json"
CHROMA_DIR = _p.episodes_db


class CoreMixin:
    """Base mixin: init, ChromaDB, index, file I/O, mood helpers."""

    def __init__(self):
        EPISODES_DIR.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()
        self.chroma_client = None
        self.milestones_collection = None

        if CHROMA_AVAILABLE:
            self._init_chroma()

    def _init_chroma(self):
        """Initialize ChromaDB for milestone search."""
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False)
        )
        self.milestones_collection = self.chroma_client.get_or_create_collection(
            name="elara_milestones",
            metadata={
                "description": "Searchable milestones from episodes",
                "hnsw:space": "cosine",
            }
        )

    def _load_index(self) -> dict:
        """Load episodes index."""
        if EPISODES_INDEX.exists():
            try:
                return json.loads(EPISODES_INDEX.read_text())
            except json.JSONDecodeError:
                pass
        return {
            "episodes": [],
            "by_project": {},
            "by_date": {},
            "last_episode_id": None,
            "total_episodes": 0,
        }

    def _save_index(self):
        """Save episodes index via atomic rename."""
        atomic_write_json(EPISODES_INDEX, self.index)

    def _get_episode_path(self, episode_id: str) -> Path:
        """Get path to episode JSON file."""
        date_part = episode_id[:7]  # "2026-02"
        month_dir = EPISODES_DIR / date_part
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"{episode_id}.json"

    def get_episode(self, episode_id: str) -> Optional[dict]:
        """Get a specific episode by ID."""
        path = self._get_episode_path(episode_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        return None

    def _save_episode(self, episode: dict) -> None:
        """Save an episode via atomic rename."""
        path = self._get_episode_path(episode["id"])
        atomic_write_json(path, episode)

    def _get_current_mood(self) -> dict:
        """Get current mood for tagging."""
        if STATE_AVAILABLE:
            try:
                return get_mood()
            except Exception:
                pass
        return {"valence": 0.5, "energy": 0.5, "openness": 0.5}
