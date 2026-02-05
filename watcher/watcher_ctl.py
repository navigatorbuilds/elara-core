#!/usr/bin/env python3
"""
Watcher control - activate, pause, status
"""

import json
import sys
from pathlib import Path

STATE_FILE = Path.home() / ".claude" / "elara-watcher-state.json"
NOTES_FILE = Path.home() / ".claude" / "elara-messages" / "notes.json"

def get_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"mode": "paused", "last_seen": None}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_latest_note():
    if NOTES_FILE.exists():
        try:
            notes = json.loads(NOTES_FILE.read_text())
            if notes:
                return notes[-1].get("timestamp")
        except:
            pass
    return None

def activate():
    """Activate watcher - start monitoring for messages."""
    state = get_state()
    state["mode"] = "active"
    state["last_seen"] = get_latest_note()  # Mark current as seen
    save_state(state)
    print("Watcher ACTIVE - monitoring for phone messages")

def pause():
    """Pause watcher - stop monitoring."""
    state = get_state()
    state["mode"] = "paused"
    save_state(state)
    print("Watcher PAUSED - not monitoring")

def status():
    """Show watcher status."""
    state = get_state()
    print(f"Mode: {state['mode'].upper()}")
    print(f"Last seen: {state.get('last_seen', 'none')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: watcher_ctl.py [activate|pause|status]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "activate":
        activate()
    elif cmd == "pause":
        pause()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
