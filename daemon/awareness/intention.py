"""
Elara Self-Awareness — Intention lens.

"What do I want to change?" — closes the loop: awareness → growth.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

INTENTION_FILE = Path.home() / ".claude" / "elara-intention.json"


def set_intention(what: str, check_previous: bool = True) -> dict:
    """
    Set a growth intention. The loop: reflect → intend → check → grow.

    Args:
        what: One specific thing to do differently
        check_previous: If True, loads previous intention and reports on it
    """
    INTENTION_FILE.parent.mkdir(parents=True, exist_ok=True)

    previous = None
    if check_previous and INTENTION_FILE.exists():
        try:
            previous = json.loads(INTENTION_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            pass

    intention = {
        "set_at": datetime.now().isoformat(),
        "what": what,
        "previous": previous,
        "checked": False,
    }

    INTENTION_FILE.write_text(json.dumps(intention, indent=2))

    result = {"current": intention}
    if previous:
        result["previous_intention"] = previous.get("what", "none")
        result["previous_set_at"] = previous.get("set_at", "unknown")

    return result


def get_intention() -> Optional[dict]:
    """Get current intention, if any."""
    if not INTENTION_FILE.exists():
        return None
    try:
        return json.loads(INTENTION_FILE.read_text())
    except (json.JSONDecodeError, Exception):
        return None
