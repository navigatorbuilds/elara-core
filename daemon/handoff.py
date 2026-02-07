"""
Elara Session Handoff — structured handoff with Pydantic schema validation.

The handoff file is Elara's short-term memory between sessions.
Previously written freeform by the LLM; now validated by Pydantic models.

- Pydantic validation ensures no missing/malformed fields
- Atomic write (temp + rename) prevents corruption
- Carry-forward logic reads previous handoff and identifies unfulfilled items
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.paths import get_paths
from daemon.events import bus, Events
from daemon.schemas import Handoff, load_validated, save_validated

logger = logging.getLogger("elara.handoff")

_p = get_paths()
HANDOFF_PATH = _p.handoff_file
HANDOFF_ARCHIVE_DIR = _p.handoff_archive


def save_handoff(data: dict) -> Dict[str, Any]:
    """
    Validate and atomically write handoff data.

    Returns {"ok": True, "path": str} on success,
    or {"ok": False, "errors": list} on validation failure.
    """
    logger.info("Saving handoff for session %s", data.get("session_number"))
    try:
        handoff = Handoff.model_validate(data)
    except Exception as e:
        logger.error("Handoff validation failed: %s", e)
        return {"ok": False, "errors": [str(e)]}

    HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Archive previous handoff before overwriting
    _archive_previous()

    try:
        save_validated(HANDOFF_PATH, handoff)
    except OSError as e:
        logger.error("Failed to save handoff to %s: %s", HANDOFF_PATH, e)
        return {"ok": False, "errors": [f"Write failed: {e}"]}

    bus.emit(Events.HANDOFF_SAVED, {
        "session_number": data.get("session_number"),
        "plans": len(data.get("next_plans", [])),
        "unfinished": len(data.get("unfinished", [])),
    }, source="handoff")
    return {"ok": True, "path": str(HANDOFF_PATH)}


def load_handoff() -> Optional[dict]:
    """Load the current handoff file. Returns None if missing or broken."""
    if not HANDOFF_PATH.exists():
        logger.debug("No handoff file at %s", HANDOFF_PATH)
        return None
    try:
        handoff = load_validated(HANDOFF_PATH, Handoff)
        return handoff.model_dump()
    except Exception as e:
        logger.error("Failed to load handoff from %s: %s", HANDOFF_PATH, e)
        return None


def get_carry_forward() -> Dict[str, Any]:
    """
    Read previous handoff and identify items that need carrying forward.

    Returns:
        {
            "previous_session": int,
            "items_to_carry": [{"text", "carried", "first_seen", "source"}],
            "mood": str,
        }
    """
    previous = load_handoff()
    if not previous:
        return {
            "previous_session": 0,
            "items_to_carry": [],
            "mood": "",
        }

    items = []
    for source in ("next_plans", "reminders", "promises", "unfinished"):
        for item in previous.get(source, []):
            if isinstance(item, dict) and item.get("text"):
                items.append({
                    "text": item["text"],
                    "carried": item.get("carried", 0) + 1,
                    "first_seen": item.get("first_seen", previous.get("timestamp", "")),
                    "source": source,
                })

    return {
        "previous_session": previous.get("session_number", 0),
        "items_to_carry": items,
        "mood": previous.get("mood_and_mode", ""),
    }


def _archive_previous():
    """Archive previous handoff to history dir."""
    if not HANDOFF_PATH.exists():
        return

    try:
        data = json.loads(HANDOFF_PATH.read_text())
        session_num = data.get("session_number", 0)
        ts = data.get("timestamp", "")[:10].replace("-", "")

        HANDOFF_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_name = f"handoff-s{session_num}-{ts}.json"
        archive_path = HANDOFF_ARCHIVE_DIR / archive_name

        if not archive_path.exists():
            archive_path.write_text(json.dumps(data, indent=2))
    except (json.JSONDecodeError, OSError):
        pass  # Don't fail on archive issues
