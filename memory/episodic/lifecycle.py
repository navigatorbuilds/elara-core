# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Episodic lifecycle — create, milestones, decisions, mood sampling, close, narrative.
"""

from datetime import datetime
from typing import List, Optional

from memory.episodic.core import LLM_AVAILABLE


class LifecycleMixin:
    """Mixin for episode lifecycle operations."""

    def create_episode(
        self,
        episode_id: str,
        session_type: str,
        started: str,
        projects: List[str] = None,
        mood_at_start: dict = None,
        continues_from: str = None,
    ) -> dict:
        """Create a new episode record."""
        episode = {
            "id": episode_id,
            "type": session_type,
            "started": started,
            "ended": None,
            "duration_minutes": None,
            "projects": projects or [],
            "tags": [],
            "mood_start": mood_at_start or self._get_current_mood(),
            "mood_end": None,
            "mood_delta": None,
            "mood_samples": [],
            "milestones": [],
            "decisions": [],
            "summary": None,
            "narrative": None,
            "continues_from": continues_from or self.index.get("last_episode_id"),
            "continued_by": None,
            "related_episodes": [],
        }

        self._get_episode_path(episode_id).write_text(
            __import__("json").dumps(episode, indent=2)
        )

        self.index["episodes"].append(episode_id)
        self.index["last_episode_id"] = episode_id
        self.index["total_episodes"] += 1

        date_key = episode_id[:10]
        if date_key not in self.index["by_date"]:
            self.index["by_date"][date_key] = []
        self.index["by_date"][date_key].append(episode_id)

        for project in (projects or []):
            if project not in self.index["by_project"]:
                self.index["by_project"][project] = []
            self.index["by_project"][project].append(episode_id)

        self._save_index()
        return episode

    def add_milestone(
        self,
        episode_id: str,
        event: str,
        milestone_type: str = "event",
        importance: float = 0.5,
        metadata: dict = None,
    ) -> dict:
        """Add a milestone to an episode."""
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        milestone = {
            "time": datetime.now().isoformat(),
            "event": event,
            "type": milestone_type,
            "importance": importance,
            "mood_at_time": self._get_current_mood(),
            "metadata": metadata or {},
        }

        episode["milestones"].append(milestone)
        self._save_episode(episode)

        if self.milestones_collection:
            milestone_id = f"{episode_id}_{len(episode['milestones'])}"
            self.milestones_collection.add(
                documents=[event],
                metadatas=[{
                    "episode_id": episode_id,
                    "type": milestone_type,
                    "importance": importance,
                    "timestamp": milestone["time"],
                    "projects": ",".join(episode.get("projects", [])),
                }],
                ids=[milestone_id]
            )

        return milestone

    def add_decision(
        self,
        episode_id: str,
        what: str,
        why: str = None,
        alternatives: List[str] = None,
        confidence: str = "medium",
        project: str = None,
    ) -> dict:
        """Record a decision made during the episode."""
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        decision = {
            "time": datetime.now().isoformat(),
            "what": what,
            "why": why,
            "alternatives_considered": alternatives or [],
            "confidence": confidence,
            "project": project,
            "mood_at_time": self._get_current_mood(),
        }

        episode["decisions"].append(decision)

        # Also add as high-importance milestone
        episode["milestones"].append({
            "time": decision["time"],
            "event": f"Decision: {what}",
            "type": "decision",
            "importance": 0.8,
            "mood_at_time": decision["mood_at_time"],
            "metadata": {"decision_index": len(episode["decisions"]) - 1},
        })

        self._save_episode(episode)

        if self.milestones_collection:
            decision_id = f"{episode_id}_decision_{len(episode['decisions'])}"
            self.milestones_collection.add(
                documents=[f"Decision: {what}. {why or ''}"],
                metadatas=[{
                    "episode_id": episode_id,
                    "type": "decision",
                    "importance": 0.8,
                    "timestamp": decision["time"],
                    "project": project or "",
                    "confidence": confidence,
                }],
                ids=[decision_id]
            )

        return decision

    def sample_mood(self, episode_id: str) -> dict:
        """Take a mood snapshot for the episode."""
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        sample = {
            "time": datetime.now().isoformat(),
            "mood": self._get_current_mood(),
        }

        episode["mood_samples"].append(sample)
        self._save_episode(episode)
        return sample

    def add_project(self, episode_id: str, project: str) -> None:
        """Add a project to the episode."""
        episode = self.get_episode(episode_id)
        if not episode:
            return

        if project not in episode["projects"]:
            episode["projects"].append(project)
            self._save_episode(episode)

            if project not in self.index["by_project"]:
                self.index["by_project"][project] = []
            if episode_id not in self.index["by_project"][project]:
                self.index["by_project"][project].append(episode_id)
            self._save_index()

    def add_tag(self, episode_id: str, tag: str) -> None:
        """Add a tag to the episode."""
        episode = self.get_episode(episode_id)
        if not episode:
            return

        if tag not in episode["tags"]:
            episode["tags"].append(tag)
            self._save_episode(episode)

    def close_episode(
        self,
        episode_id: str,
        summary: str = None,
        narrative: str = None,
        mood_end: dict = None,
    ) -> dict:
        """Close an episode, finalizing its record."""
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        try:
            started = datetime.fromisoformat(episode["started"])
            duration = int((datetime.now() - started).total_seconds() / 60)
        except (ValueError, TypeError):
            duration = 0

        episode["ended"] = datetime.now().isoformat()
        episode["duration_minutes"] = duration
        episode["mood_end"] = mood_end or self._get_current_mood()
        episode["summary"] = summary
        episode["narrative"] = narrative or self._generate_narrative(episode)

        if episode["mood_start"] and episode["mood_end"]:
            episode["mood_delta"] = round(
                episode["mood_end"]["valence"] - episode["mood_start"]["valence"],
                3
            )

        self._save_episode(episode)
        return episode

    def _generate_narrative(self, episode: dict) -> str:
        """Generate a narrative summary. Tries Ollama first, falls back to template."""
        if LLM_AVAILABLE:
            try:
                from daemon import llm
                narrative = llm.generate_narrative(episode)
                if narrative:
                    return narrative
            except Exception:
                pass

        return self._generate_narrative_template(episode)

    def _generate_narrative_template(self, episode: dict) -> str:
        """Template-based narrative (fallback when Ollama unavailable)."""
        parts = []

        duration = episode.get("duration_minutes", 0)
        session_type = episode.get("type", "mixed")
        parts.append(f"{session_type.title()} session, {duration} minutes.")

        projects = episode.get("projects", [])
        if projects:
            parts.append(f"Worked on: {', '.join(projects)}.")

        milestones = episode.get("milestones", [])
        important = [m for m in milestones if m.get("importance", 0) >= 0.7]
        if important:
            events = [m["event"] for m in important[:3]]
            parts.append(f"Key moments: {'; '.join(events)}.")

        decisions = episode.get("decisions", [])
        if decisions:
            decision_summaries = [d["what"] for d in decisions[:2]]
            parts.append(f"Decided: {'; '.join(decision_summaries)}.")

        if episode.get("mood_delta"):
            delta = episode["mood_delta"]
            if delta > 0.2:
                parts.append("Mood improved significantly.")
            elif delta > 0:
                parts.append("Mood slightly better by end.")
            elif delta < -0.2:
                parts.append("Challenging session, mood dropped.")
            elif delta < 0:
                parts.append("Slightly harder session.")

        return " ".join(parts)
