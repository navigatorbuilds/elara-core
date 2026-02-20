# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Brain Scheduler — always-on 24/7 daemon.

Runs the 32b model continuously. Thinks every INTERVAL_HOURS (default 2h).
No longer blocked by active Claude sessions — the GPU can handle both.

Control:
  - Kill switch: ~/.claude/overnight/brain-pause
    Touch file → brain pauses. Remove → brain resumes.
    Elara can do this on "stop 32b" / "start 32b" commands.

  - Quiet hours: 3-6 AM (configurable) — no new runs start.

  - Config: ~/.claude/overnight/overnight-config.json
    "schedule_mode": "continuous" (default now)
    "interval_hours": 2 (how often to run)
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

# Set up logging — only for the brain scheduler logger, not root
# (avoids double-logging when OvernightRunner adds its own handlers)
logger = logging.getLogger("elara.brain")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(str(LOG_FILE), mode="a")
    _fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_fh)
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_sh)

_p = get_paths()

# --- Configuration ---

# Default interval between thinking runs
DEFAULT_INTERVAL_HOURS = 2.0

# Quiet hours disabled — runs accumulate, nothing is overwritten.
# To pause, use the brain-pause file instead.
QUIET_HOURS_START = None
QUIET_HOURS_END = None

# How often to check (seconds)
POLL_INTERVAL = 60

# Only log waiting status every N minutes (not every minute)
LOG_INTERVAL_MINUTES = 15

# Kill switch file — touch to pause, rm to resume
PAUSE_FILE = OVERNIGHT_DIR / "brain-pause"

# Last run tracking
LAST_RUN_META = OVERNIGHT_DIR / "last-run-meta.json"


def _is_paused() -> bool:
    """Check if the brain is paused via kill switch file."""
    return PAUSE_FILE.exists()


def _last_thinking_run() -> datetime | None:
    """When did we last complete a thinking run?"""
    # Check the canonical last-run-meta.json first
    if LAST_RUN_META.exists():
        try:
            data = json.loads(LAST_RUN_META.read_text())
            return datetime.fromisoformat(data.get("ended", data.get("started", "")))
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    # Fallback: check today's meta.json
    today = OVERNIGHT_DIR / datetime.now().strftime("%Y-%m-%d") / "meta.json"
    if today.exists():
        try:
            data = json.loads(today.read_text())
            return datetime.fromisoformat(data.get("ended", data.get("started", "")))
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    return None


def _write_last_run_meta():
    """Write last-run tracking file after a successful run."""
    LAST_RUN_META.write_text(json.dumps({
        "ended": datetime.now().isoformat(),
        "started": datetime.now().isoformat(),
    }))


def _in_quiet_hours() -> bool:
    """Check if we're in the no-start window. Disabled — always returns False."""
    if QUIET_HOURS_START is None:
        return False
    hour = datetime.now().hour
    return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def _should_think(interval_hours: float = DEFAULT_INTERVAL_HOURS) -> tuple[bool, str]:
    """
    Decide whether to start a thinking run.
    Simple: respect pause file, quiet hours, and interval. That's it.
    """
    # Kill switch
    if _is_paused():
        return False, "paused (brain-pause file exists)"

    # Quiet hours
    if _in_quiet_hours():
        return False, "quiet hours (3-6 AM)"

    # Check interval since last run
    last_run = _last_thinking_run()
    if last_run:
        gap_hours = (datetime.now() - last_run).total_seconds() / 3600
        if gap_hours < interval_hours:
            remaining = interval_hours - gap_hours
            return False, f"next run in {remaining:.1f}h ({gap_hours:.1f}h since last)"
        return True, f"interval reached ({gap_hours:.1f}h since last, threshold: {interval_hours}h)"

    # No previous run found — run now
    return True, "no previous run found — starting first run"


class BrainScheduler:
    """Always-on 24/7 scheduler. Thinks every N hours, no session gating."""

    def __init__(self):
        self.stop_event = threading.Event()
        self.running = False
        self._last_log_time = None

    def _handle_signal(self, signum, frame):
        logger.info("Signal %d received — shutting down", signum)
        self.stop_event.set()

    def run(self):
        """Main loop — poll, decide, think, repeat."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        sched_pid = OVERNIGHT_DIR / "scheduler.pid"
        OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
        sched_pid.write_text(str(os.getpid()))

        logger.info("=== Brain scheduler started (PID %d) ===", os.getpid())
        quiet_str = f"{QUIET_HOURS_START}-{QUIET_HOURS_END}" if QUIET_HOURS_START is not None else "disabled"
        logger.info("Mode: continuous | Interval: configurable | Quiet: %s", quiet_str)
        logger.info("Pause control: %s", PAUSE_FILE)

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
        while not self.stop_event.is_set():
            config = load_config()
            interval = config.get("interval_hours", DEFAULT_INTERVAL_HOURS)

            should, reason = _should_think(interval)

            if should:
                logger.info("Triggering thinking run — %s", reason)
                self._run_thinking()
                self._last_log_time = None  # Reset log timer after run
            else:
                self._log_waiting(reason)

            self.stop_event.wait(POLL_INTERVAL)

    def _log_waiting(self, reason: str):
        """Log waiting status, but only every LOG_INTERVAL_MINUTES to avoid spam."""
        now = datetime.now()
        if self._last_log_time is None or \
           (now - self._last_log_time).total_seconds() >= LOG_INTERVAL_MINUTES * 60:
            logger.info("Waiting — %s", reason)
            self._last_log_time = now

    def _run_thinking(self):
        """Run the overnight thinking system."""
        self.running = True

        # Cortical Layer 3 — emit brain start event
        try:
            from daemon.events import bus, Events
            bus.emit(Events.BRAIN_THINKING_STARTED, {
                "timestamp": datetime.now().isoformat(),
            }, source="brain.scheduler")
        except Exception:
            pass

        try:
            from daemon.overnight import OvernightRunner
            runner = OvernightRunner()
            runner.stop_event = self.stop_event
            result = runner.run()
            logger.info("Thinking complete: %s", result)

            # Write last-run tracking so interval timer works
            _write_last_run_meta()

            # Cortical Layer 3 — emit brain complete event
            try:
                from daemon.events import bus, Events
                bus.emit(Events.BRAIN_THINKING_COMPLETED, {
                    "timestamp": datetime.now().isoformat(),
                    "result": str(result)[:200] if result else None,
                }, source="brain.scheduler")
            except Exception:
                pass

        except Exception as e:
            logger.error("Thinking run failed: %s", e)
        finally:
            self.running = False
