#!/usr/bin/env python3
"""
Worker control - activate, pause, status, reset
"""

import json
import sys
from pathlib import Path

STATE_FILE = Path.home() / ".claude" / "elara-worker-state.json"
LOG_FILE = Path.home() / ".claude" / "elara-worker.log"


def get_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"mode": "paused", "last_seen_note": None, "is_first_message": True}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def activate():
    """Activate worker - start processing messages."""
    state = get_state()
    state["mode"] = "active"
    save_state(state)
    print("Worker ACTIVE - processing phone messages")


def pause():
    """Pause worker - stop processing."""
    state = get_state()
    state["mode"] = "paused"
    save_state(state)
    print("Worker PAUSED")


def reset():
    """Reset worker - clear state, start fresh session."""
    state = {
        "mode": "paused",
        "last_seen_note": None,
        "is_first_message": True,
        "tasks_completed": 0,
    }
    save_state(state)
    print("Worker RESET - next message starts fresh session")


def status():
    """Show worker status."""
    state = get_state()
    print(f"Mode: {state['mode'].upper()}")
    print(f"First message: {state.get('is_first_message', True)}")
    print(f"Last seen: {state.get('last_seen_note', 'none')}")
    print(f"Tasks completed: {state.get('tasks_completed', 0)}")


def logs(n=20):
    """Show recent logs."""
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        for line in lines[-n:]:
            print(line)
    else:
        print("No logs yet")


def usage():
    print("Usage: worker_ctl.py [activate|pause|status|reset|logs]")
    print()
    print("Commands:")
    print("  activate  - Start processing phone messages")
    print("  pause     - Stop processing (worker keeps running)")
    print("  status    - Show current state")
    print("  reset     - Clear state, next message starts fresh Claude session")
    print("  logs      - Show recent worker logs")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "activate":
        activate()
    elif cmd == "pause":
        pause()
    elif cmd == "status":
        status()
    elif cmd == "reset":
        reset()
    elif cmd == "logs":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        logs(n)
    else:
        print(f"Unknown command: {cmd}")
        usage()
