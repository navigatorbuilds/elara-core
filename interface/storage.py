# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Message Storage
Persistent storage for notes and messages so they survive restarts.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from core.paths import get_paths

logger = logging.getLogger("elara.interface.storage")

STORAGE_DIR = get_paths().messages_dir
NOTES_FILE = STORAGE_DIR / "notes.json"
MESSAGES_FILE = STORAGE_DIR / "elara_messages.json"


def _ensure_storage():
    """Ensure storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> List[Dict[str, Any]]:
    """Load JSON file or return empty list."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return []


def _save_json(path: Path, data: List[Dict[str, Any]]) -> None:
    """Save data to JSON file."""
    _ensure_storage()
    path.write_text(json.dumps(data, indent=2))


# Notes (from user's phone)
def get_notes() -> List[Dict[str, Any]]:
    """Get all saved notes."""
    return _load_json(NOTES_FILE)


def add_note(text: str) -> Dict[str, Any]:
    """Add a new note."""
    notes = get_notes()
    note = {
        "time": datetime.now().strftime("%H:%M"),
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
    notes.append(note)
    # Keep last 100 notes
    notes = notes[-100:]
    _save_json(NOTES_FILE, notes)
    return note


def get_recent_notes(n: int = 10) -> List[Dict[str, Any]]:
    """Get last N notes."""
    return get_notes()[-n:]


# Elara messages (to user's phone)
def get_messages() -> List[Dict[str, Any]]:
    """Get all Elara messages."""
    return _load_json(MESSAGES_FILE)


def add_message(text: str) -> Dict[str, Any]:
    """Add a new message from Elara."""
    messages = get_messages()
    msg = {
        "time": datetime.now().strftime("%H:%M"),
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "read": False
    }
    messages.append(msg)
    # Keep last 100 messages
    messages = messages[-100:]
    _save_json(MESSAGES_FILE, messages)
    return msg


def get_recent_messages(n: int = 10) -> List[Dict[str, Any]]:
    """Get last N messages."""
    return get_messages()[-n:]


def get_unread_messages() -> List[Dict[str, Any]]:
    """Get unread messages."""
    return [m for m in get_messages() if not m.get("read", True)]


def mark_messages_read() -> None:
    """Mark all messages as read."""
    messages = get_messages()
    for m in messages:
        m["read"] = True
    _save_json(MESSAGES_FILE, messages)


# Test
if __name__ == "__main__":
    print("Testing storage...")
    add_note("Test note from phone")
    add_message("Test message from Elara")
    print(f"Notes: {get_recent_notes()}")
    print(f"Messages: {get_recent_messages()}")
