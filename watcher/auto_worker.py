#!/usr/bin/env python3
"""
Auto Worker Manager
- Pauses worker when terminal is active (you're typing)
- Resumes worker when idle (you've been away)

This prevents two Claudes running simultaneously.
"""

import subprocess
import time
import os
from pathlib import Path
from datetime import datetime

# Config
IDLE_THRESHOLD = 120  # seconds of no terminal activity before resuming worker
CHECK_INTERVAL = 10   # how often to check
STATE_FILE = Path.home() / ".claude" / "elara-worker-state.json"
TMUX_SESSION = os.environ.get("ELARA_TMUX_SESSION", "elara")

def log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def get_terminal_idle_seconds() -> int:
    """Get seconds since last terminal activity in tmux."""
    try:
        # Check tmux pane activity (when output last changed)
        result = subprocess.run(
            ["tmux", "display-message", "-t", TMUX_SESSION, "-p", "#{pane_activity}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            last_active = int(result.stdout.strip())
            now = int(time.time())
            idle = now - last_active
            return idle
    except Exception as e:
        log(f"Error checking idle: {e}")
    return 0

def is_worker_active() -> bool:
    """Check if worker is in active mode."""
    if STATE_FILE.exists():
        try:
            import json
            state = json.loads(STATE_FILE.read_text())
            return state.get("mode") == "active"
        except:
            pass
    return False

def worker_ctl(cmd: str):
    """Run worker control command."""
    try:
        subprocess.run(
            ["python", "/home/neboo/elara-core/watcher/worker_ctl.py", cmd],
            capture_output=True,
            timeout=10
        )
    except Exception as e:
        log(f"Worker ctl error: {e}")

def run_auto_manager():
    """Main loop."""
    log("=" * 50)
    log("Auto Worker Manager")
    log(f"Idle threshold: {IDLE_THRESHOLD}s")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log("=" * 50)

    was_idle = False

    while True:
        try:
            idle_seconds = get_terminal_idle_seconds()
            is_idle = idle_seconds >= IDLE_THRESHOLD
            worker_active = is_worker_active()

            # Transition: became idle -> activate worker
            if is_idle and not was_idle:
                if not worker_active:
                    log(f"Terminal idle ({idle_seconds}s) - activating worker")
                    worker_ctl("activate")

            # Transition: became active -> pause worker
            elif not is_idle and was_idle:
                if worker_active:
                    log(f"Terminal active - pausing worker")
                    worker_ctl("pause")

            was_idle = is_idle
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log("Auto manager stopped")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_auto_manager()
