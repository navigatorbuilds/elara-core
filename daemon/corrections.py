"""
Elara Corrections System - Learn from mistakes, never repeat them.

Storage: ~/.claude/elara-corrections.json
High-priority memories that never decay. Max 50 entries (oldest archived).
Loaded at boot so I don't repeat mistakes.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

CORRECTIONS_FILE = Path.home() / ".claude" / "elara-corrections.json"
MAX_CORRECTIONS = 50


def _load() -> List[Dict]:
    if not CORRECTIONS_FILE.exists():
        return []
    with open(CORRECTIONS_FILE, "r") as f:
        return json.load(f)


def _save(corrections: List[Dict]):
    CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CORRECTIONS_FILE, "w") as f:
        json.dump(corrections, f, indent=2)


def add_correction(
    mistake: str,
    correction: str,
    context: Optional[str] = None,
) -> Dict:
    """Record a correction. Never decays."""
    corrections = _load()

    entry = {
        "id": len(corrections) + 1,
        "mistake": mistake,
        "correction": correction,
        "context": context,
        "date": datetime.now().isoformat(),
    }
    corrections.append(entry)

    # Cap at MAX_CORRECTIONS, remove oldest
    if len(corrections) > MAX_CORRECTIONS:
        corrections = corrections[-MAX_CORRECTIONS:]

    _save(corrections)
    return entry


def list_corrections(n: int = 20) -> List[Dict]:
    """Get recent corrections."""
    corrections = _load()
    return corrections[-n:]


def boot_corrections(n: int = 10) -> str:
    """Get corrections for boot loading. Short format."""
    corrections = _load()
    recent = corrections[-n:]

    if not recent:
        return ""

    lines = ["Don't repeat these:"]
    for c in recent:
        lines.append(f"  - {c['mistake']} → {c['correction']}")

    return "\n".join(lines)


def search_corrections(keyword: str) -> List[Dict]:
    """Simple keyword search through corrections."""
    corrections = _load()
    keyword_lower = keyword.lower()
    return [
        c for c in corrections
        if keyword_lower in c["mistake"].lower()
        or keyword_lower in c["correction"].lower()
        or keyword_lower in (c.get("context") or "").lower()
    ]
