"""
Elara Session Handoff — structured handoff with schema validation.

The handoff file is Elara's short-term memory between sessions.
Previously written freeform by the LLM; now validated by code.

- Schema validation ensures no missing/malformed fields
- Atomic write (temp + rename) prevents corruption
- Carry-forward logic reads previous handoff and identifies unfulfilled items
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

HANDOFF_PATH = Path.home() / ".claude" / "elara-handoff.json"
HANDOFF_ARCHIVE_DIR = Path.home() / ".claude" / "elara-handoff-archive"

# Required top-level fields and their types
SCHEMA = {
    "timestamp": str,
    "session_number": int,
    "next_plans": list,
    "reminders": list,
    "mood_and_mode": str,
    "promises": list,
    "unfinished": list,
}

# Required fields per list item
ITEM_FIELDS = {"text": str, "carried": int, "first_seen": str}


def _validate_item(item: dict, field_name: str) -> List[str]:
    """Validate a single list item (plan, reminder, etc.)."""
    errors = []
    if not isinstance(item, dict):
        errors.append(f"{field_name}: item is not a dict: {type(item)}")
        return errors

    for key, expected_type in ITEM_FIELDS.items():
        if key not in item:
            errors.append(f"{field_name}: missing '{key}'")
        elif not isinstance(item[key], expected_type):
            errors.append(f"{field_name}.{key}: expected {expected_type.__name__}, got {type(item[key]).__name__}")

    # Validate carried >= 0
    if isinstance(item.get("carried"), int) and item["carried"] < 0:
        errors.append(f"{field_name}: carried cannot be negative")

    # Validate first_seen is ISO format
    first_seen = item.get("first_seen", "")
    if isinstance(first_seen, str) and first_seen:
        try:
            datetime.fromisoformat(first_seen)
        except ValueError:
            errors.append(f"{field_name}: first_seen is not valid ISO format: {first_seen}")

    # Validate optional expires field (ISO timestamp)
    expires = item.get("expires")
    if expires is not None:
        if not isinstance(expires, str):
            errors.append(f"{field_name}: expires must be an ISO timestamp string")
        else:
            try:
                datetime.fromisoformat(expires)
            except ValueError:
                errors.append(f"{field_name}: expires is not valid ISO format: {expires}")

    return errors


def validate_handoff(data: dict) -> List[str]:
    """
    Validate handoff data against schema.

    Returns list of error strings. Empty list = valid.
    """
    errors = []

    # Check top-level fields
    for field, expected_type in SCHEMA.items():
        if field not in data:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(data[field], expected_type):
            errors.append(f"Field '{field}': expected {expected_type.__name__}, got {type(data[field]).__name__}")

    if errors:
        return errors  # Can't validate items if top-level is broken

    # Validate timestamp is ISO
    try:
        datetime.fromisoformat(data["timestamp"])
    except ValueError:
        errors.append(f"timestamp is not valid ISO format: {data['timestamp']}")

    # Validate session_number > 0
    if data["session_number"] <= 0:
        errors.append(f"session_number must be positive: {data['session_number']}")

    # Validate list items
    for list_field in ("next_plans", "reminders", "promises", "unfinished"):
        for i, item in enumerate(data[list_field]):
            item_errors = _validate_item(item, f"{list_field}[{i}]")
            errors.extend(item_errors)

    return errors


def save_handoff(data: dict) -> Dict[str, Any]:
    """
    Validate and atomically write handoff data.

    Returns {"ok": True, "path": str} on success,
    or {"ok": False, "errors": list} on validation failure.
    """
    errors = validate_handoff(data)
    if errors:
        return {"ok": False, "errors": errors}

    HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Archive previous handoff before overwriting
    _archive_previous()

    # Atomic write: temp file + rename
    tmp = HANDOFF_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        os.rename(str(tmp), str(HANDOFF_PATH))
    except OSError as e:
        return {"ok": False, "errors": [f"Write failed: {e}"]}

    return {"ok": True, "path": str(HANDOFF_PATH)}


def load_handoff() -> Optional[dict]:
    """Load the current handoff file. Returns None if missing or broken."""
    if not HANDOFF_PATH.exists():
        return None
    try:
        return json.loads(HANDOFF_PATH.read_text())
    except (json.JSONDecodeError, OSError):
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
