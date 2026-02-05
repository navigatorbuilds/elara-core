#!/usr/bin/env python3
"""
Elara Phone Watcher
Monitors for new phone messages and pokes the terminal when one arrives.
Only active when in AWAY mode.
"""

import json
import time
import subprocess
import os
from pathlib import Path
from datetime import datetime

# Config
CHECK_INTERVAL = 3  # seconds between checks
STATE_FILE = Path.home() / ".claude" / "elara-watcher-state.json"
NOTES_FILE = Path.home() / ".claude" / "elara-messages" / "notes.json"
TMUX_SESSION = os.environ.get("ELARA_TMUX_SESSION", "elara")

def get_state():
    """Get watcher state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"mode": "paused", "last_seen": None}

def save_state(state):
    """Save watcher state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_latest_note():
    """Get the latest note timestamp."""
    if NOTES_FILE.exists():
        try:
            notes = json.loads(NOTES_FILE.read_text())
            if notes:
                return notes[-1].get("timestamp")
        except:
            pass
    return None

def poke_terminal():
    """Send a poke to the tmux session."""
    try:
        # Send the phone emoji as a trigger
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, "📱 new message", "C-m"],
            capture_output=True,
            timeout=5
        )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Poked terminal")
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Poke failed: {e}")
        return False

def run_watcher():
    """Main watcher loop."""
    print("=" * 50)
    print("Elara Phone Watcher")
    print(f"Checking every {CHECK_INTERVAL}s")
    print(f"State file: {STATE_FILE}")
    print(f"Tmux session: {TMUX_SESSION}")
    print("=" * 50)

    while True:
        try:
            state = get_state()

            if state["mode"] == "active":
                latest = get_latest_note()

                if latest and latest != state.get("last_seen"):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] New message detected!")
                    if poke_terminal():
                        state["last_seen"] = latest
                        save_state(state)

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nWatcher stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_watcher()
