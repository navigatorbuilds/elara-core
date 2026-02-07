"""
Elara Episodic Memory - Rich autobiographical memory for work sessions.

This is where I remember what happened, not just what I know.
"I remember the apartments conversation — the frustration, the decision, the relief."

Two-track system:
- Work sessions: Full episodic (milestones, decisions, context)
- Drift sessions: Soft episodic (imprints only, preserved in state.py)
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import hashlib

# ChromaDB for searchable content
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

# Import state for mood context
try:
    from daemon.state import get_mood, get_current_episode
    STATE_AVAILABLE = True
except ImportError:
    STATE_AVAILABLE = False

EPISODES_DIR = Path.home() / ".claude" / "elara-episodes"
EPISODES_INDEX = EPISODES_DIR / "index.json"
CHROMA_DIR = Path.home() / ".claude" / "elara-episodes-db"


class EpisodicMemory:
    """
    Rich episodic memory system.

    Stores full episodes (sessions) with:
    - Milestones (significant events)
    - Decisions (choices made)
    - Mood trajectory
    - Project context
    - Narrative summary
    """

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
            "episodes": [],  # List of episode IDs
            "by_project": {},  # project -> [episode_ids]
            "by_date": {},  # date -> [episode_ids]
            "last_episode_id": None,
            "total_episodes": 0,
        }

    def _save_index(self):
        """Save episodes index via atomic rename."""
        tmp_file = EPISODES_INDEX.with_suffix(".json.tmp")
        tmp_file.write_text(json.dumps(self.index, indent=2))
        os.rename(str(tmp_file), str(EPISODES_INDEX))

    def _get_episode_path(self, episode_id: str) -> Path:
        """Get path to episode JSON file."""
        # Organize by month: episodes/2026-02/2026-02-05-0941.json
        date_part = episode_id[:7]  # "2026-02"
        month_dir = EPISODES_DIR / date_part
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"{episode_id}.json"

    def _get_current_mood(self) -> dict:
        """Get current mood for tagging."""
        if STATE_AVAILABLE:
            try:
                return get_mood()
            except Exception:
                pass
        return {"valence": 0.5, "energy": 0.5, "openness": 0.5}

    # =========================================================================
    # EPISODE LIFECYCLE
    # =========================================================================

    def create_episode(
        self,
        episode_id: str,
        session_type: str,
        started: str,
        projects: List[str] = None,
        mood_at_start: dict = None,
        continues_from: str = None,
    ) -> dict:
        """
        Create a new episode record.

        Called when start_episode() is triggered in state.py.
        """
        episode = {
            "id": episode_id,
            "type": session_type,  # "work", "drift", "mixed"
            "started": started,
            "ended": None,
            "duration_minutes": None,

            # Context
            "projects": projects or [],
            "tags": [],

            # Mood trajectory
            "mood_start": mood_at_start or self._get_current_mood(),
            "mood_end": None,
            "mood_delta": None,
            "mood_samples": [],  # Periodic mood snapshots

            # Content (for work sessions)
            "milestones": [],
            "decisions": [],

            # Narrative
            "summary": None,
            "narrative": None,  # Rich description generated at end

            # Threading
            "continues_from": continues_from or self.index.get("last_episode_id"),
            "continued_by": None,
            "related_episodes": [],
        }

        # Save episode
        self._get_episode_path(episode_id).write_text(json.dumps(episode, indent=2))

        # Update index
        self.index["episodes"].append(episode_id)
        self.index["last_episode_id"] = episode_id
        self.index["total_episodes"] += 1

        # Index by date
        date_key = episode_id[:10]  # "2026-02-05"
        if date_key not in self.index["by_date"]:
            self.index["by_date"][date_key] = []
        self.index["by_date"][date_key].append(episode_id)

        # Index by projects
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
        """
        Add a milestone to an episode.

        Milestones are significant events worth remembering:
        - Task completed
        - Decision made
        - Problem solved
        - Error encountered
        - Insight gained

        Args:
            episode_id: The episode to add to
            event: Description of what happened
            milestone_type: "event", "completion", "decision", "insight", "error"
            importance: 0-1, affects recall priority
            metadata: Additional context
        """
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

        # Index in ChromaDB for search
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
        """
        Record a decision made during the episode.

        Decisions are choices that affect future work:
        - Architecture choices
        - Feature decisions
        - Process changes
        - Priorities set
        """
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        decision = {
            "time": datetime.now().isoformat(),
            "what": what,
            "why": why,
            "alternatives_considered": alternatives or [],
            "confidence": confidence,  # "low", "medium", "high"
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

        # Index decision in ChromaDB
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

            # Update index
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
        """
        Close an episode, finalizing its record.

        Args:
            episode_id: The episode to close
            summary: Brief summary (1-2 sentences)
            narrative: Rich description of what happened
            mood_end: Final mood state
        """
        episode = self.get_episode(episode_id)
        if not episode:
            return {"error": f"Episode {episode_id} not found"}

        # Calculate duration
        try:
            started = datetime.fromisoformat(episode["started"])
            duration = int((datetime.now() - started).total_seconds() / 60)
        except (ValueError, TypeError):
            duration = 0

        # Finalize episode
        episode["ended"] = datetime.now().isoformat()
        episode["duration_minutes"] = duration
        episode["mood_end"] = mood_end or self._get_current_mood()
        episode["summary"] = summary
        episode["narrative"] = narrative or self._generate_narrative(episode)

        # Calculate mood delta
        if episode["mood_start"] and episode["mood_end"]:
            episode["mood_delta"] = round(
                episode["mood_end"]["valence"] - episode["mood_start"]["valence"],
                3
            )

        self._save_episode(episode)

        return episode

    def _generate_narrative(self, episode: dict) -> str:
        """Generate a narrative summary from episode data."""
        parts = []

        # Session type and duration
        duration = episode.get("duration_minutes", 0)
        session_type = episode.get("type", "mixed")
        parts.append(f"{session_type.title()} session, {duration} minutes.")

        # Projects
        projects = episode.get("projects", [])
        if projects:
            parts.append(f"Worked on: {', '.join(projects)}.")

        # Key milestones
        milestones = episode.get("milestones", [])
        important = [m for m in milestones if m.get("importance", 0) >= 0.7]
        if important:
            events = [m["event"] for m in important[:3]]
            parts.append(f"Key moments: {'; '.join(events)}.")

        # Decisions
        decisions = episode.get("decisions", [])
        if decisions:
            decision_summaries = [d["what"] for d in decisions[:2]]
            parts.append(f"Decided: {'; '.join(decision_summaries)}.")

        # Mood trajectory
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

    # =========================================================================
    # RETRIEVAL
    # =========================================================================

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
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(episode, indent=2))
        os.rename(str(tmp_path), str(path))

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

        # Collect decisions
        all_decisions = []
        for ep in episodes:
            all_decisions.extend(ep.get("decisions", []))

        # Collect high-importance milestones
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
            recent = all_decisions[:3]
            for d in recent:
                parts.append(f"  - {d['what']}")

        if key_milestones:
            parts.append(f"Key milestones: {len(key_milestones)}")
            recent = key_milestones[:3]
            for m in recent:
                parts.append(f"  - {m['event']}")

        return "\n".join(parts)

    # =========================================================================
    # NARRATIVE THREADING
    # =========================================================================

    def link_episodes(self, episode_id: str, related_id: str) -> None:
        """Link two episodes as related."""
        ep1 = self.get_episode(episode_id)
        ep2 = self.get_episode(related_id)

        if ep1 and ep2:
            if related_id not in ep1.get("related_episodes", []):
                ep1["related_episodes"].append(related_id)
                self._save_episode(ep1)

            if episode_id not in ep2.get("related_episodes", []):
                ep2["related_episodes"].append(episode_id)
                self._save_episode(ep2)

    def get_episode_thread(self, episode_id: str, depth: int = 5) -> List[dict]:
        """Get the thread of episodes (previous → current → next)."""
        thread = []
        current_id = episode_id

        # Walk backwards
        backwards = []
        for _ in range(depth):
            ep = self.get_episode(current_id)
            if not ep:
                break
            backwards.append(ep)
            current_id = ep.get("continues_from")
            if not current_id:
                break

        thread = list(reversed(backwards))

        # Walk forwards from original
        current_id = episode_id
        for _ in range(depth):
            ep = self.get_episode(current_id)
            if not ep:
                break
            continued_by = ep.get("continued_by")
            if not continued_by:
                break
            next_ep = self.get_episode(continued_by)
            if next_ep:
                thread.append(next_ep)
            current_id = continued_by

        return thread

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_stats(self) -> dict:
        """Get episodic memory statistics."""
        total = self.index.get("total_episodes", 0)
        projects = list(self.index.get("by_project", {}).keys())

        # Count milestones
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
    if STATE_AVAILABLE:
        try:
            current = get_current_episode()
            if current:
                return get_episodic().add_milestone(current["id"], event, **kwargs)
        except Exception:
            pass
    return {"error": "No active episode"}


def decision(what: str, **kwargs) -> dict:
    """Quick decision recording for current episode."""
    if STATE_AVAILABLE:
        try:
            current = get_current_episode()
            if current:
                return get_episodic().add_decision(current["id"], what, **kwargs)
        except Exception:
            pass
    return {"error": "No active episode"}


# Test
if __name__ == "__main__":
    print("Testing episodic memory...")
    em = EpisodicMemory()
    print(f"Stats: {em.get_stats()}")
