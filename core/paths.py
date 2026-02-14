# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Paths — single source of truth for all data file locations.

Resolution order:
  1. ELARA_DATA_DIR environment variable
  2. Default: ~/.elara/

Usage:
    from core.paths import get_paths
    p = get_paths()
    p.state_file        # ~/.elara/elara-state.json
    p.dreams_dir        # ~/.elara/elara-dreams/
    p.claude_projects   # ~/.claude/projects  (Claude Code data, never changes)

For tests:
    from core.paths import configure
    configure(tmp_path)  # all paths now rooted under tmp_path
"""

import os
from pathlib import Path
from typing import Optional


class ElaraPaths:
    """Central registry of every file and directory Elara uses."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is not None:
            self._root = Path(data_dir)
        else:
            env = os.environ.get("ELARA_DATA_DIR")
            if env:
                self._root = Path(env).expanduser()
            else:
                self._root = Path.home() / ".elara"

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Claude Code integration (always under ~/.claude, not ELARA_DATA_DIR)
    # ------------------------------------------------------------------
    @property
    def claude_projects(self) -> Path:
        return Path.home() / ".claude" / "projects"

    # ------------------------------------------------------------------
    # Core state files
    # ------------------------------------------------------------------
    @property
    def state_file(self) -> Path:
        return self._root / "elara-state.json"

    @property
    def mood_journal(self) -> Path:
        return self._root / "elara-mood-journal.jsonl"

    @property
    def imprint_archive(self) -> Path:
        return self._root / "elara-imprint-archive.jsonl"

    @property
    def temperament_log(self) -> Path:
        return self._root / "elara-temperament-log.jsonl"

    @property
    def presence_file(self) -> Path:
        return self._root / "elara-presence.json"

    @property
    def session_state(self) -> Path:
        return self._root / "elara-session-state.json"

    @property
    def user_state_file(self) -> Path:
        return self._root / "elara-user-state.json"

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    @property
    def context_file(self) -> Path:
        return self._root / "elara-context.json"

    @property
    def context_config(self) -> Path:
        return self._root / "elara-context-config.json"

    # ------------------------------------------------------------------
    # Handoff
    # ------------------------------------------------------------------
    @property
    def handoff_file(self) -> Path:
        return self._root / "elara-handoff.json"

    @property
    def handoff_archive(self) -> Path:
        return self._root / "elara-handoff-archive"

    # ------------------------------------------------------------------
    # Goals, corrections, intention
    # ------------------------------------------------------------------
    @property
    def goals_file(self) -> Path:
        return self._root / "elara-goals.json"

    @property
    def corrections_file(self) -> Path:
        return self._root / "elara-corrections.json"

    @property
    def corrections_db(self) -> Path:
        return self._root / "elara-corrections-db"

    @property
    def intention_file(self) -> Path:
        return self._root / "elara-intention.json"

    # ------------------------------------------------------------------
    # Awareness / proactive
    # ------------------------------------------------------------------
    @property
    def proactive_session(self) -> Path:
        return self._root / "elara-proactive-session.json"

    @property
    def blind_spots_file(self) -> Path:
        return self._root / "elara-blind-spots.json"

    @property
    def pulse_file(self) -> Path:
        return self._root / "elara-pulse.json"

    @property
    def reflections_dir(self) -> Path:
        return self._root / "elara-reflections"

    # ------------------------------------------------------------------
    # Memory databases
    # ------------------------------------------------------------------
    @property
    def memory_db(self) -> Path:
        return self._root / "elara-memory-db"

    @property
    def recall_log(self) -> Path:
        return self._root / "elara-recall-log.jsonl"

    @property
    def consolidation_state(self) -> Path:
        return self._root / "elara-consolidation-state.json"

    @property
    def memory_archive(self) -> Path:
        return self._root / "elara-memory-archive.jsonl"

    @property
    def memory_contradictions(self) -> Path:
        return self._root / "elara-memory-contradictions.json"

    @property
    def conversations_db(self) -> Path:
        return self._root / "elara-conversations-db"

    @property
    def episodes_dir(self) -> Path:
        return self._root / "elara-episodes"

    @property
    def episodes_db(self) -> Path:
        return self._root / "elara-episodes-db"

    @property
    def episodes_archive(self) -> Path:
        return self._root / "elara-episodes-archive.jsonl"

    # ------------------------------------------------------------------
    # Dreams
    # ------------------------------------------------------------------
    @property
    def dreams_dir(self) -> Path:
        return self._root / "elara-dreams"

    @property
    def dreams_weekly(self) -> Path:
        return self.dreams_dir / "weekly"

    @property
    def dreams_monthly(self) -> Path:
        return self.dreams_dir / "monthly"

    @property
    def dreams_threads(self) -> Path:
        return self.dreams_dir / "threads"

    @property
    def dreams_emotional(self) -> Path:
        return self.dreams_dir / "emotional"

    @property
    def dream_status(self) -> Path:
        return self.dreams_dir / "status.json"

    # ------------------------------------------------------------------
    # Cognitive (reasoning, outcomes, synthesis)
    # ------------------------------------------------------------------
    @property
    def reasoning_dir(self) -> Path:
        return self._root / "elara-reasoning"

    @property
    def reasoning_db(self) -> Path:
        return self._root / "elara-reasoning-db"

    @property
    def outcomes_dir(self) -> Path:
        return self._root / "elara-outcomes"

    @property
    def synthesis_dir(self) -> Path:
        return self._root / "elara-synthesis"

    @property
    def synthesis_db(self) -> Path:
        return self._root / "elara-synthesis-db"

    # ------------------------------------------------------------------
    # Business
    # ------------------------------------------------------------------
    @property
    def business_dir(self) -> Path:
        return self._root / "elara-business"

    # ------------------------------------------------------------------
    # Briefing
    # ------------------------------------------------------------------
    @property
    def feeds_config(self) -> Path:
        return self._root / "elara-feeds.json"

    @property
    def briefing_db(self) -> Path:
        return self._root / "elara-briefing-db"

    @property
    def briefing_file(self) -> Path:
        return self._root / "elara-briefing.json"

    @property
    def briefing_log(self) -> Path:
        return self._root / "elara-briefing.log"

    # ------------------------------------------------------------------
    # Gmail
    # ------------------------------------------------------------------
    @property
    def gmail_credentials(self) -> Path:
        return self._root / "elara-gmail-credentials.json"

    @property
    def gmail_token(self) -> Path:
        return self._root / "elara-gmail-token.json"

    @property
    def gmail_db(self) -> Path:
        return self._root / "elara-gmail-db"

    @property
    def gmail_cache(self) -> Path:
        return self._root / "elara-gmail-cache.json"

    # ------------------------------------------------------------------
    # Overnight
    # ------------------------------------------------------------------
    @property
    def overnight_dir(self) -> Path:
        return self._root / "overnight"

    @property
    def overnight_pid(self) -> Path:
        return self.overnight_dir / "overnight.pid"

    @property
    def overnight_log(self) -> Path:
        return self.overnight_dir / "overnight.log"

    @property
    def overnight_config(self) -> Path:
        return self.overnight_dir / "overnight-config.json"

    @property
    def overnight_queue(self) -> Path:
        return self.overnight_dir / "overnight-queue.json"

    @property
    def overnight_latest(self) -> Path:
        return self.overnight_dir / "latest-findings.md"

    # ------------------------------------------------------------------
    # 3D Cognition (models, predictions, principles)
    # ------------------------------------------------------------------
    @property
    def models_dir(self) -> Path:
        return self._root / "elara-models"

    @property
    def models_db(self) -> Path:
        return self._root / "elara-models-db"

    @property
    def predictions_dir(self) -> Path:
        return self._root / "elara-predictions"

    @property
    def predictions_db(self) -> Path:
        return self._root / "elara-predictions-db"

    @property
    def principles_file(self) -> Path:
        return self._root / "elara-principles.json"

    @property
    def principles_db(self) -> Path:
        return self._root / "elara-principles-db"

    @property
    def morning_brief(self) -> Path:
        return self.overnight_dir / "morning-brief.md"

    @property
    def creative_journal(self) -> Path:
        return self.overnight_dir / "creative-journal.md"

    # ------------------------------------------------------------------
    # Overwatch
    # ------------------------------------------------------------------
    @property
    def overwatch_inject(self) -> Path:
        return self._root / "elara-overwatch-inject.md"

    @property
    def overwatch_pid(self) -> Path:
        return self._root / "elara-overwatch.pid"

    @property
    def overwatch_log(self) -> Path:
        return self._root / "elara-overwatch.log"

    @property
    def session_snapshot(self) -> Path:
        return self._root / "elara-session-snapshot.json"

    # ------------------------------------------------------------------
    # Interface / storage
    # ------------------------------------------------------------------
    @property
    def messages_dir(self) -> Path:
        return self._root / "elara-messages"

    @property
    def daemon_log(self) -> Path:
        return self._root / "elara-daemon.log"

    # ------------------------------------------------------------------
    # Persona / relationship files (user-managed, lives in data dir)
    # ------------------------------------------------------------------
    @property
    def us_file(self) -> Path:
        return self._root / "us.md"

    # ------------------------------------------------------------------
    # Directory creation
    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        """Create all required directories."""
        dirs = [
            self.data_dir,
            self.handoff_archive,
            self.corrections_db,
            self.reflections_dir,
            self.memory_db,
            self.conversations_db,
            self.episodes_dir,
            self.episodes_db,
            self.dreams_dir,
            self.dreams_weekly,
            self.dreams_monthly,
            self.dreams_threads,
            self.dreams_emotional,
            self.reasoning_dir,
            self.reasoning_db,
            self.outcomes_dir,
            self.synthesis_dir,
            self.synthesis_db,
            self.business_dir,
            self.briefing_db,
            self.gmail_db,
            self.messages_dir,
            self.overnight_dir,
            self.models_dir,
            self.models_db,
            self.predictions_dir,
            self.predictions_db,
            self.principles_db,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Singleton
# ===========================================================================

_instance: Optional[ElaraPaths] = None


def get_paths() -> ElaraPaths:
    """Return the global ElaraPaths singleton (lazy-init)."""
    global _instance
    if _instance is None:
        _instance = ElaraPaths()
    return _instance


def configure(data_dir: Path) -> ElaraPaths:
    """
    Override the global paths singleton. Used by tests and CLI --data-dir.

    Returns the new instance for convenience.
    """
    global _instance
    _instance = ElaraPaths(data_dir=data_dir)
    return _instance


def reset() -> None:
    """Reset singleton so next get_paths() re-reads env."""
    global _instance
    _instance = None
