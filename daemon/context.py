#!/usr/bin/env python3
"""
Elara Quick Context
Lightweight moment-to-moment tracking for session continuity.

This is NOT long-term memory - it's just "what were we doing 5 seconds ago"
when you switch terminals or I time out.

Default: ON
Toggle: elara-context on/off
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from daemon.schemas import (
    Context, ContextConfig, load_validated, save_validated,
)

CONTEXT_FILE = Path.home() / ".claude" / "elara-context.json"
CONFIG_FILE = Path.home() / ".claude" / "elara-context-config.json"


def is_enabled() -> bool:
    """Check if context tracking is enabled. Default: ON"""
    if CONFIG_FILE.exists():
        config = load_validated(CONFIG_FILE, ContextConfig)
        return config.enabled
    return True  # Default ON


def set_enabled(enabled: bool):
    """Enable or disable context tracking."""
    model = ContextConfig(enabled=enabled)
    save_validated(CONFIG_FILE, model)


def save_context(
    topic: Optional[str] = None,
    last_exchange: Optional[str] = None,
    task_in_progress: Optional[str] = None
):
    """
    Save current context. Called on session end or topic shift.

    Args:
        topic: What we're working on (e.g., "testing nuclear worker")
        last_exchange: Brief note on last interaction
        task_in_progress: Active task if any
    """
    if not is_enabled():
        return

    # Load existing to preserve fields not being updated
    current = get_context()

    if topic is not None:
        current["topic"] = topic
    if last_exchange is not None:
        current["last_exchange"] = last_exchange
    if task_in_progress is not None:
        current["task_in_progress"] = task_in_progress

    current["updated"] = datetime.now().isoformat()
    current["updated_ts"] = int(datetime.now().timestamp())

    model = Context.model_validate(current)
    save_validated(CONTEXT_FILE, model)


def get_context() -> Dict[str, Any]:
    """Get saved context."""
    model = load_validated(CONTEXT_FILE, Context)
    return model.model_dump()


def get_gap_seconds() -> Optional[int]:
    """Get seconds since last context save."""
    ctx = get_context()
    if ctx.get("updated_ts"):
        return int(datetime.now().timestamp()) - ctx["updated_ts"]
    return None


def get_gap_description() -> str:
    """Human-readable gap description."""
    gap = get_gap_seconds()
    if gap is None:
        return "unknown"

    if gap < 60:
        return f"{gap} seconds"
    elif gap < 3600:
        return f"{gap // 60} minutes"
    elif gap < 86400:
        return f"{gap // 3600} hours"
    else:
        return f"{gap // 86400} days"


def format_for_boot() -> Dict[str, Any]:
    """
    Format context for boot script output.
    Returns gap info and context appropriate for the gap length.
    """
    if not is_enabled():
        return {"enabled": False}

    ctx = get_context()
    gap = get_gap_seconds()

    result = {
        "enabled": True,
        "gap_seconds": gap,
        "gap_description": get_gap_description()
    }

    # Only include context details for short gaps
    if gap is not None:
        if gap < 120:  # < 2 min - instant resume
            result["mode"] = "instant"
            result["topic"] = ctx.get("topic")
            result["last_exchange"] = ctx.get("last_exchange")
        elif gap < 1200:  # < 20 min - quick return
            result["mode"] = "quick"
            result["topic"] = ctx.get("topic")
        elif gap < 7200:  # < 2 hours - same session
            result["mode"] = "return"
            result["topic"] = ctx.get("topic")
        else:  # longer - full boot
            result["mode"] = "full"
    else:
        result["mode"] = "full"

    return result


def clear_context():
    """Clear saved context."""
    if CONTEXT_FILE.exists():
        CONTEXT_FILE.unlink()


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: context.py [on|off|status|clear|save]")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "on":
        set_enabled(True)
        print("Context tracking: ON")
    elif cmd == "off":
        set_enabled(False)
        print("Context tracking: OFF")
    elif cmd == "status":
        enabled = is_enabled()
        ctx = get_context()
        gap = get_gap_description()
        print(f"Enabled: {enabled}")
        print(f"Gap: {gap}")
        print(f"Topic: {ctx.get('topic', 'none')}")
        print(f"Last: {ctx.get('last_exchange', 'none')}")
    elif cmd == "clear":
        clear_context()
        print("Context cleared")
    elif cmd == "save":
        # save topic last_exchange
        topic = sys.argv[2] if len(sys.argv) > 2 else None
        last_exchange = sys.argv[3] if len(sys.argv) > 3 else None
        save_context(topic=topic, last_exchange=last_exchange)
        print(f"Saved: {topic}")
    else:
        print(f"Unknown command: {cmd}")
