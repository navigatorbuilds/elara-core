# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Episodic Memory - Rich autobiographical memory for work sessions.

Split into mixins:
- CoreMixin (core.py) — init, ChromaDB, index, file I/O, mood helpers
- LifecycleMixin (lifecycle.py) — create, milestones, decisions, close, narrative
- RetrievalMixin (retrieval.py) — get, search, project queries
- ThreadingMixin (threading.py) — link episodes, walk chains
- CompressionMixin (compression.py) — archive, compress, cleanup
"""

from memory.episodic.core import CoreMixin, STATE_AVAILABLE
from memory.episodic.lifecycle import LifecycleMixin
from memory.episodic.retrieval import RetrievalMixin
from memory.episodic.threading import ThreadingMixin
from memory.episodic.compression import CompressionMixin

try:
    from daemon.state import get_current_episode
except ImportError:
    get_current_episode = None


class EpisodicMemory(CoreMixin, LifecycleMixin, RetrievalMixin, ThreadingMixin, CompressionMixin):
    """
    Rich episodic memory system.

    Stores full episodes (sessions) with milestones, decisions,
    mood trajectory, project context, and narrative summaries.
    """

    def get_stats(self) -> dict:
        """Get episodic memory statistics."""
        total = self.index.get("total_episodes", 0)
        projects = list(self.index.get("by_project", {}).keys())

        milestone_count = 0
        if self.milestones_collection:
            milestone_count = self.milestones_collection.count()

        return {
            "total_episodes": total,
            "projects_tracked": len(projects),
            "projects": projects,
            "milestone_count": milestone_count,
            "last_episode": self.index.get("last_episode_id"),
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_episodic = None


def get_episodic() -> EpisodicMemory:
    """Get or create the global episodic memory instance."""
    global _episodic
    if _episodic is None:
        _episodic = EpisodicMemory()
    return _episodic


def milestone(event: str, **kwargs) -> dict:
    """Quick milestone recording for current episode."""
    if STATE_AVAILABLE and get_current_episode:
        try:
            current = get_current_episode()
            if current:
                return get_episodic().add_milestone(current["id"], event, **kwargs)
        except Exception:
            pass
    return {"error": "No active episode"}


def decision(what: str, **kwargs) -> dict:
    """Quick decision recording for current episode."""
    if STATE_AVAILABLE and get_current_episode:
        try:
            current = get_current_episode()
            if current:
                return get_episodic().add_decision(current["id"], what, **kwargs)
        except Exception:
            pass
    return {"error": "No active episode"}
