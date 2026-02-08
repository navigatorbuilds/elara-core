# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Conversation Memory — Episode Cross-Referencing mixin.

Links conversations to episodic milestones by timestamp overlap.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from memory.conversations.core import EPISODES_DIR, EPISODES_INDEX


class CrossRefMixin:
    """Mixin providing episode cross-referencing capabilities."""

    def _load_episode_ranges(self) -> List[Dict[str, Any]]:
        """
        Load episode time ranges for cross-referencing.
        Returns list of {id, started, ended} dicts.
        """
        if not EPISODES_INDEX.exists():
            return []

        try:
            index = json.loads(EPISODES_INDEX.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        ranges = []
        for episode_id in index.get("episodes", []):
            # Load episode file to get time range
            date_part = episode_id[:7]
            ep_path = EPISODES_DIR / date_part / f"{episode_id}.json"
            if not ep_path.exists():
                continue

            try:
                ep = json.loads(ep_path.read_text())
                started = ep.get("started", "")
                ended = ep.get("ended", "")
                ranges.append({
                    "id": episode_id,
                    "started": started,
                    "ended": ended,
                    "projects": ep.get("projects", []),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return ranges

    def _match_episode(self, timestamp: str, episode_ranges: List[Dict]) -> Optional[str]:
        """
        Find which episode a conversation timestamp belongs to.
        Returns episode_id or None.
        """
        if not timestamp or not episode_ranges:
            return None

        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Remove timezone for comparison since episodes use naive timestamps
            if ts.tzinfo:
                ts = ts.replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

        for ep in episode_ranges:
            try:
                started = datetime.fromisoformat(ep["started"])
                if ep["ended"]:
                    ended = datetime.fromisoformat(ep["ended"])
                else:
                    # Open episode — assume it's the current one
                    ended = datetime.now()

                if started <= ts <= ended:
                    return ep["id"]
            except (ValueError, TypeError):
                continue

        return None

    def get_conversations_for_episode(
        self,
        episode_id: str,
        n_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get all conversation exchanges that happened during a specific episode.
        """
        if not self.collection:
            return []

        try:
            results = self.collection.get(
                where={"episode_id": episode_id},
                include=["documents", "metadatas"],
                limit=n_results,
            )
        except Exception:
            return []

        exchanges = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                exchanges.append({
                    "content": doc,
                    "exchange_index": meta.get("exchange_index", 0),
                    "timestamp": meta.get("timestamp", ""),
                    "session_id": meta.get("session_id", ""),
                })

        exchanges.sort(key=lambda x: x["exchange_index"])
        return exchanges

    def get_episodes_for_session(self, session_id: str) -> List[str]:
        """
        Get all episode IDs that overlap with a session.
        """
        if not self.collection:
            return []

        try:
            results = self.collection.get(
                where={"session_id": session_id},
                include=["metadatas"],
            )
        except Exception:
            return []

        episode_ids = set()
        if results["metadatas"]:
            for meta in results["metadatas"]:
                ep_id = meta.get("episode_id", "")
                if ep_id:
                    episode_ids.add(ep_id)

        return sorted(episode_ids)
