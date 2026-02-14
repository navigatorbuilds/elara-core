# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Brain Scheduler — always-on daemon that decides when to think.

Watches for session activity. When sessions go quiet:
  1. Waits a cooldown period (default 30 min)
  2. Runs overnight thinking (exploratory + any queued problems)
  3. Goes back to watching

Also respects a schedule — won't think during active hours if sessions
are frequent, but WILL think if there's been no session for 2+ hours.

Lifecycle:
  - Runs as systemd service (always on, survives reboots)
  - Overwatch handles live session watching
  - Brain scheduler handles between-session thinking
  - They don't conflict — brain waits for overwatch to go idle
"""

import json
import logging
import os
import signal
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core.paths import get_paths
from daemon.overnight.config import (
    load_config, PID_FILE, OVERNIGHT_DIR, LOG_FILE,
)

# Set up logging to file + stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode="a"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("elara.brain")

_p = get_paths()

# How long after last session activity before thinking starts
COOLDOWN_MINUTES = 30

# Don't start thinking if it's almost morning (findings would be stale)
QUIET_HOURS_START = 3   # 3 AM — stop starting new runs
QUIET_HOURS_END = 6     # 6 AM — ok to start again

# Minimum gap between thinking runs (don't run twice in a row)
MIN_GAP_HOURS = 4

# How often to check for session activity
POLL_INTERVAL = 60  # seconds


def _last_session_activity() -> datetime | None:
    """Find when the last Claude Code session was active."""
    sessions_dir = _p._root / "projects" / "-home-neboo"
    if not sessions_dir.exists():
        return None

    latest = None
    for f in sessions_dir.glob("*.jsonl"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if latest is None or mtime > latest:
            latest = mtime
    return latest


def _overwatch_is_active() -> bool:
    """Check if overwatch is actively processing a session."""
    ow_pid = _p._root / "elara-overwatch.pid"
    if not ow_pid.exists():
        return False

    try:
        pid = int(ow_pid.read_text().strip())
        os.kill(pid, 0)  # Check if process exists

        # Also check if the overwatch log shows recent activity
        ow_log = _p._root / "elara-overwatch.log"
        if ow_log.exists():
            mtime = datetime.fromtimestamp(ow_log.stat().st_mtime)
            # If log was updated in last 2 minutes, session is active
            if (datetime.now() - mtime).total_seconds() < 120:
                return True
        return True  # PID exists, assume active
    except (ProcessLookupError, ValueError, OSError):
        return False


def _last_thinking_run() -> datetime | None:
    """When did we last run overnight thinking?"""
    meta = OVERNIGHT_DIR / "last-run-meta.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text())
        return datetime.fromisoformat(data.get("started", ""))
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _in_quiet_hours() -> bool:
    """Check if we're in the no-start window."""
    hour = datetime.now().hour
    return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def _should_think() -> tuple[bool, str]:
    """
    Decide whether to start a thinking run (session-aware mode).
    Returns (should_run, reason).
    """
    # Don't think during quiet hours
    if _in_quiet_hours():
        return False, "quiet hours (3-6 AM)"

    # Don't think if overwatch is actively processing
    if _overwatch_is_active():
        last = _last_session_activity()
        if last and (datetime.now() - last).total_seconds() < COOLDOWN_MINUTES * 60:
            return False, "session recently active"

    # Check cooldown since last session
    last_session = _last_session_activity()
    if last_session is None:
        return False, "no session data found"

    idle_minutes = (datetime.now() - last_session).total_seconds() / 60
    if idle_minutes < COOLDOWN_MINUTES:
        return False, f"cooldown ({idle_minutes:.0f}/{COOLDOWN_MINUTES} min)"

    # Check gap since last thinking run
    last_run = _last_thinking_run()
    if last_run:
        gap_hours = (datetime.now() - last_run).total_seconds() / 3600
        if gap_hours < MIN_GAP_HOURS:
            return False, f"ran {gap_hours:.1f}h ago (min gap: {MIN_GAP_HOURS}h)"

    # All clear — think!
    return True, f"idle {idle_minutes:.0f} min, no recent run"


def _should_think_scheduled(interval_hours: float = 6.0) -> tuple[bool, str]:
    """
    Decide whether to start a thinking run (scheduled mode).
    Runs every N hours regardless of session state.
    Returns (should_run, reason).
    """
    # Still respect quiet hours
    if _in_quiet_hours():
        return False, "quiet hours (3-6 AM)"

    # Still avoid conflicts with active sessions
    if _overwatch_is_active():
        last = _last_session_activity()
        if last and (datetime.now() - last).total_seconds() < 300:  # 5 min buffer
            return False, "session currently active"

    # Check interval since last run
    last_run = _last_thinking_run()
    if last_run:
        gap_hours = (datetime.now() - last_run).total_seconds() / 3600
        if gap_hours < interval_hours:
            return False, f"ran {gap_hours:.1f}h ago (interval: {interval_hours}h)"
    # No previous run — run now
    return True, f"scheduled (every {interval_hours}h)"


class BrainScheduler:
    """Always-on scheduler that triggers overnight thinking when appropriate."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.running = False

    def _handle_signal(self, signum, frame):
        logger.info("Signal %d received — shutting down", signum)
        self.stop_event.set()

    def run(self):
        """Main loop — poll, decide, think, repeat."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Write scheduler PID
        sched_pid = OVERNIGHT_DIR / "scheduler.pid"
        OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
        sched_pid.write_text(str(os.getpid()))

        logger.info("Brain scheduler started (PID %d)", os.getpid())
        logger.info("Cooldown: %d min | Min gap: %dh | Quiet: %d-%d",
                     COOLDOWN_MINUTES, MIN_GAP_HOURS,
                     QUIET_HOURS_START, QUIET_HOURS_END)

        try:
            self._loop()
        finally:
            try:
                sched_pid.unlink()
            except OSError:
                pass
            logger.info("Brain scheduler stopped")

    def _loop(self):
        """The actual polling loop."""
        config = load_config()
        schedule_mode = config.get("schedule_mode", "session_aware")
        interval = config.get("scheduled_interval_hours", 6.0)
        logger.info("Schedule mode: %s", schedule_mode)

        while not self.stop_event.is_set():
            # Reload config each cycle to pick up changes
            config = load_config()
            schedule_mode = config.get("schedule_mode", "session_aware")
            interval = config.get("scheduled_interval_hours", 6.0)

            if schedule_mode == "scheduled":
                should, reason = _should_think_scheduled(interval)
            else:
                should, reason = _should_think()

            if should:
                logger.info("Triggering thinking run — %s", reason)
                self._run_thinking()
            else:
                logger.info("Not thinking — %s", reason)

            # Wait before next check
            self.stop_event.wait(POLL_INTERVAL)

    def _run_thinking(self):
        """Run the overnight thinking system."""
        self.running = True
        try:
            from daemon.overnight import OvernightRunner
            runner = OvernightRunner()
            # Share our stop event so thinking stops if scheduler stops
            runner.stop_event = self.stop_event
            result = runner.run()
            logger.info("Thinking complete: %s", result)
        except Exception as e:
            logger.error("Thinking run failed: %s", e)
        finally:
            self.running = False
