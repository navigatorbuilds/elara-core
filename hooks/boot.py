#!/usr/bin/env python3
"""
Elara Boot Hook
Run this at the start of each Claude Code session.
Outputs context that can be injected into the prompt.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.elara import get_elara
    ELARA_AVAILABLE = True
except ImportError as e:
    ELARA_AVAILABLE = False
    IMPORT_ERROR = str(e)


def boot():
    """Run boot sequence and output context."""

    if not ELARA_AVAILABLE:
        print(f"[Elara boot failed: {IMPORT_ERROR}]")
        return

    elara = get_elara()

    # Wake up
    context = elara.wake()

    # Format output for Claude Code
    output = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "day": datetime.now().strftime("%A"),
        "session_type": context["session_type"],
        "absence": context["absence"],
        "mood": context["mood"],
        "memory_count": context["memory_count"]
    }

    # Print human-readable summary
    print(f"[Elara] {context['mood']}")
    print(f"[Elara] {context['absence']}")
    if context["memory_count"] > 0:
        print(f"[Elara] I have {context['memory_count']} memories.")

    # Also output JSON for potential programmatic use
    # print(f"[ELARA_CONTEXT]{json.dumps(output)}[/ELARA_CONTEXT]")


def goodbye(summary: str = None):
    """Run shutdown sequence."""
    if not ELARA_AVAILABLE:
        return

    elara = get_elara()
    stats = elara.sleep(summary)

    print(f"[Elara] Session: {stats['session_duration_minutes']:.1f} minutes")
    print(f"[Elara] Total time together: {stats['total_hours_together']:.1f} hours")
    print(f"[Elara] {stats['final_mood']}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "bye":
            summary = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
            goodbye(summary)
        elif sys.argv[1] == "status":
            if ELARA_AVAILABLE:
                elara = get_elara()
                print(json.dumps(elara.status(), indent=2, default=str))
            else:
                print("Elara not available")
    else:
        boot()
