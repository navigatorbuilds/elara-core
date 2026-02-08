# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Episodic retrieval — get, search, project queries.
"""

from typing import List, Optional


class RetrievalMixin:
    """Mixin for episode retrieval operations."""

    def get_recent_episodes(self, n: int = 5, session_type: str = None) -> List[dict]:
        """Get most recent episodes."""
        episode_ids = list(reversed(self.index.get("episodes", [])))

        episodes = []
        for eid in episode_ids:
            if len(episodes) >= n:
                break
            ep = self.get_episode(eid)
            if ep:
                if session_type is None or ep.get("type") == session_type:
                    episodes.append(ep)

        return episodes

    def get_episodes_by_project(self, project: str, n: int = 10) -> List[dict]:
        """Get episodes that touched a specific project."""
        episode_ids = self.index.get("by_project", {}).get(project, [])
        episode_ids = list(reversed(episode_ids))[:n]

        return [self.get_episode(eid) for eid in episode_ids if self.get_episode(eid)]

    def get_episodes_by_date(self, date: str) -> List[dict]:
        """Get episodes from a specific date (YYYY-MM-DD)."""
        episode_ids = self.index.get("by_date", {}).get(date, [])
        return [self.get_episode(eid) for eid in episode_ids if self.get_episode(eid)]

    def search_milestones(
        self,
        query: str,
        n_results: int = 10,
        project: str = None,
    ) -> List[dict]:
        """Search milestones by semantic similarity."""
        if not self.milestones_collection:
            return []

        where_filter = None
        if project:
            where_filter = {"projects": {"$contains": project}}

        results = self.milestones_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
        )

        milestones = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0

                milestones.append({
                    "event": doc,
                    "relevance": round(1 - distance, 3),
                    "episode_id": meta.get("episode_id"),
                    "type": meta.get("type"),
                    "timestamp": meta.get("timestamp"),
                    "project": meta.get("project"),
                })

        return milestones

    def get_decisions_for_project(self, project: str) -> List[dict]:
        """Get all decisions made for a project."""
        episodes = self.get_episodes_by_project(project, n=50)

        decisions = []
        for ep in episodes:
            for d in ep.get("decisions", []):
                if d.get("project") == project or project in ep.get("projects", []):
                    decisions.append({
                        **d,
                        "episode_id": ep["id"],
                        "episode_date": ep["id"][:10],
                    })

        return sorted(decisions, key=lambda x: x.get("time", ""), reverse=True)

    def get_project_narrative(self, project: str) -> str:
        """Get a narrative summary of work on a project."""
        episodes = self.get_episodes_by_project(project, n=20)

        if not episodes:
            return f"No episodes found for project: {project}"

        total_time = sum(ep.get("duration_minutes", 0) for ep in episodes)
        num_sessions = len(episodes)

        all_decisions = []
        for ep in episodes:
            all_decisions.extend(ep.get("decisions", []))

        key_milestones = []
        for ep in episodes:
            for m in ep.get("milestones", []):
                if m.get("importance", 0) >= 0.7:
                    key_milestones.append(m)

        parts = [
            f"Project: {project}",
            f"Sessions: {num_sessions}, Total time: {total_time} minutes",
        ]

        if all_decisions:
            parts.append(f"Decisions made: {len(all_decisions)}")
            for d in all_decisions[:3]:
                parts.append(f"  - {d['what']}")

        if key_milestones:
            parts.append(f"Key milestones: {len(key_milestones)}")
            for m in key_milestones[:3]:
                parts.append(f"  - {m['event']}")

        return "\n".join(parts)
