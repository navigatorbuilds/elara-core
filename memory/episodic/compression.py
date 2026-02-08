# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Episodic compression — archive old episodes, strip heavy fields.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

from core.paths import get_paths
from memory.episodic.core import LLM_AVAILABLE


ARCHIVE_FILE = get_paths().episodes_archive


class CompressionMixin:
    """Mixin for episode compression and archival."""

    def compress_old_episodes(self, days: int = 60) -> dict:
        """
        Compress episodes older than N days.

        - Archive full episode to JSONL
        - Strip milestones/decisions, keep summary + key_metrics
        - Remove milestone vectors from ChromaDB
        - Save compressed version back
        """
        cutoff = datetime.now() - timedelta(days=days)
        stats = {"compressed": 0, "archived": 0, "milestones_removed": 0}

        for episode_id in self.index.get("episodes", []):
            episode = self.get_episode(episode_id)
            if not episode or episode.get("compressed"):
                continue

            ended = episode.get("ended")
            if not ended:
                continue

            try:
                ended_dt = datetime.fromisoformat(ended)
            except (ValueError, TypeError):
                continue

            if ended_dt >= cutoff:
                continue

            self._archive_episode(episode)
            stats["archived"] += 1

            removed = self._remove_episode_milestones(episode_id, episode)
            stats["milestones_removed"] += removed

            compressed = self._compress_episode(episode)
            self._save_episode(compressed)
            stats["compressed"] += 1

        return stats

    def _archive_episode(self, episode: dict) -> None:
        """Append full episode JSON to archive JSONL file."""
        ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ARCHIVE_FILE, "a") as f:
            f.write(json.dumps(episode) + "\n")

    def _compress_episode(self, episode: dict) -> dict:
        """Strip heavy fields, keep essential metadata."""
        milestone_count = len(episode.get("milestones", []))
        decision_count = len(episode.get("decisions", []))

        summary = episode.get("summary")
        if LLM_AVAILABLE and milestone_count > 0:
            try:
                from daemon import llm
                events = "; ".join(m["event"] for m in episode.get("milestones", [])[:5])
                llm_summary = llm.summarize(
                    f"Session ({episode.get('type', 'work')}, {episode.get('duration_minutes', 0)} min, "
                    f"projects: {', '.join(episode.get('projects', []))}). "
                    f"Events: {events}",
                    max_sentences=2,
                )
                if llm_summary:
                    summary = llm_summary
            except Exception:
                pass

        return {
            "id": episode["id"],
            "type": episode.get("type"),
            "started": episode.get("started"),
            "ended": episode.get("ended"),
            "duration_minutes": episode.get("duration_minutes"),
            "projects": episode.get("projects", []),
            "tags": episode.get("tags", []),
            "mood_start": episode.get("mood_start"),
            "mood_end": episode.get("mood_end"),
            "mood_delta": episode.get("mood_delta"),
            "summary": summary,
            "continues_from": episode.get("continues_from"),
            "continued_by": episode.get("continued_by"),
            "compressed": True,
            "key_metrics": {
                "milestone_count": milestone_count,
                "decision_count": decision_count,
            },
        }

    def _remove_episode_milestones(self, episode_id: str, episode: dict) -> int:
        """Delete this episode's milestones from ChromaDB."""
        if not self.milestones_collection:
            return 0

        milestones = episode.get("milestones", [])
        decisions = episode.get("decisions", [])
        if not milestones and not decisions:
            return 0

        ids_to_remove = []
        for i in range(1, len(milestones) + 1):
            ids_to_remove.append(f"{episode_id}_{i}")
        for i in range(1, len(decisions) + 1):
            ids_to_remove.append(f"{episode_id}_decision_{i}")

        if not ids_to_remove:
            return 0

        try:
            self.milestones_collection.delete(ids=ids_to_remove)
        except Exception:
            pass

        return len(ids_to_remove)
