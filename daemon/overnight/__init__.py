# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Overnight — autonomous thinking system.

Gathers all knowledge, runs themed thinking phases through a local LLM,
writes findings for morning review.

Usage:
    python3 -m daemon.overnight          # auto mode
    python3 -m daemon.overnight --mode exploratory
    python3 -m daemon.overnight --mode directed
"""

import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from daemon.overnight.config import (
    setup_logging, load_config, load_queue,
    PID_FILE, OVERNIGHT_DIR,
)
from daemon.overnight.gather import gather_all, format_context_for_prompt
from daemon.overnight.thinker import OvernightThinker
from daemon.overnight.output import write_findings, write_meta

logger = logging.getLogger("elara.overnight")


class OvernightRunner:
    """Orchestrator — manages the full overnight thinking run."""

    def __init__(self, mode_override: str = None):
        self.config = load_config()
        self.queue = load_queue()
        self.stop_event = threading.Event()
        self.started = datetime.now()

        # Determine mode
        if mode_override:
            self.mode = mode_override
        elif self.config.get("mode", "auto") != "auto":
            self.mode = self.config["mode"]
        else:
            # Auto: directed if queue has items, else exploratory
            self.mode = "directed" if self.queue else "exploratory"

        logger.info("Overnight runner initialized — mode: %s", self.mode)

    def _write_pid(self):
        """Write PID file."""
        OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        logger.info("PID %d written to %s", os.getpid(), PID_FILE)

    def _cleanup_pid(self):
        """Remove PID file."""
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except OSError:
            pass

    def _setup_signals(self):
        """Register signal handlers for graceful stop."""
        def _handle_stop(signum, frame):
            logger.info("Received signal %d — stopping after current round", signum)
            self.stop_event.set()

        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)

    def _check_ollama(self) -> bool:
        """Verify Ollama is available."""
        from daemon.llm import is_available, _last_check
        # Force a fresh check
        import daemon.llm as llm_mod
        llm_mod._last_check = 0

        if not is_available():
            logger.error("Ollama not available — cannot run overnight thinking")
            return False
        logger.info("Ollama available")
        return True

    def _run_prerequisites(self):
        """Run overdue dreams and briefing fetch."""
        logger.info("Checking prerequisites...")

        # Check for overdue dreams
        try:
            from daemon.dream_core import dream_status
            ds = dream_status()

            if ds.get("weekly_overdue"):
                logger.info("Running overdue weekly dream...")
                from daemon.dream_weekly import weekly_dream
                weekly_dream()
                logger.info("Weekly dream complete")

            if ds.get("monthly_overdue"):
                logger.info("Running overdue monthly dream...")
                from daemon.dream_monthly import monthly_dream
                monthly_dream()
                logger.info("Monthly dream complete")
        except Exception as e:
            logger.warning("Dream prerequisites failed: %s", e)

        # Fetch briefings
        try:
            from daemon.briefing import fetch_all
            result = fetch_all()
            fetched = result.get("fetched", 0)
            if fetched:
                logger.info("Briefing fetch: %d new items", fetched)
        except Exception as e:
            logger.warning("Briefing fetch failed: %s", e)

    def run(self) -> dict:
        """
        Main run method. Returns summary dict.
        """
        self._setup_signals()
        self._write_pid()

        try:
            return self._run_inner()
        finally:
            self._cleanup_pid()

    def _run_inner(self) -> dict:
        """Inner run logic (PID + signals already set up)."""
        # Check Ollama
        if not self._check_ollama():
            write_meta(self.started, self.config, self.mode, 0, status="error")
            return {"status": "error", "reason": "Ollama not available"}

        # Prerequisites
        self._run_prerequisites()

        if self.stop_event.is_set():
            write_meta(self.started, self.config, self.mode, 0, status="stopped")
            return {"status": "stopped", "reason": "Stopped during prerequisites"}

        # Gather knowledge
        context = gather_all(days=30)
        context_text = format_context_for_prompt(context, max_chars=6000)
        logger.info("Context formatted: %d chars", len(context_text))

        if not context_text.strip():
            logger.error("No context gathered — nothing to think about")
            write_meta(self.started, self.config, self.mode, 0, status="error")
            return {"status": "error", "reason": "No context available"}

        # Create thinker
        thinker = OvernightThinker(context_text, self.config, self.stop_event)

        all_rounds = []
        problems_processed = 0
        problems_list = []

        # Run exploratory
        if self.mode in ("exploratory", "auto"):
            exploratory_rounds = thinker.run_exploratory()
            all_rounds.extend(exploratory_rounds)

        # Run directed
        if self.mode in ("directed", "auto") and self.queue:
            directed_rounds = thinker.run_directed(self.queue)
            all_rounds.extend(directed_rounds)
            problems_list = [
                item.get("problem", str(item)) if isinstance(item, dict) else str(item)
                for item in self.queue
            ]
            problems_processed = len(set(
                r.get("problem", "") for r in directed_rounds if r.get("problem")
            ))

        # Write outputs
        if all_rounds:
            findings_mode = "mixed" if self.mode == "auto" and self.queue else self.mode
            write_findings(all_rounds, mode=findings_mode, problems=problems_list or None)

        status = "completed" if not self.stop_event.is_set() else "stopped"
        write_meta(
            self.started, self.config, self.mode,
            rounds_completed=thinker.total_rounds,
            problems_processed=problems_processed,
            research_queries=thinker.total_research_queries,
            status=status,
        )

        elapsed = (datetime.now() - self.started).total_seconds() / 60
        logger.info("=== OVERNIGHT COMPLETE ===")
        logger.info("  Mode: %s", self.mode)
        logger.info("  Rounds: %d", thinker.total_rounds)
        logger.info("  Research queries: %d", thinker.total_research_queries)
        logger.info("  Duration: %.1f minutes", elapsed)
        logger.info("  Status: %s", status)

        return {
            "status": status,
            "mode": self.mode,
            "rounds": thinker.total_rounds,
            "research_queries": thinker.total_research_queries,
            "problems_processed": problems_processed,
            "duration_minutes": round(elapsed, 1),
        }
