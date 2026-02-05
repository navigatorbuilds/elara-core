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

try:
    from daemon.context import format_for_boot, is_enabled as context_enabled
    CONTEXT_AVAILABLE = True
except ImportError:
    CONTEXT_AVAILABLE = False

try:
    from memory.conversations import get_conversations
    CONVERSATIONS_AVAILABLE = True
except ImportError:
    CONVERSATIONS_AVAILABLE = False


def boot():
    """Run boot sequence and output context."""

    if not ELARA_AVAILABLE:
        print(f"[Elara boot failed: {IMPORT_ERROR}]")
        return

    elara = get_elara()

    # Wake up
    context = elara.wake()

    # Get quick context for gap-aware greeting
    if CONTEXT_AVAILABLE:
        quick_ctx = format_for_boot()

        if quick_ctx.get("enabled"):
            gap = quick_ctx.get("gap_seconds")
            mode = quick_ctx.get("mode", "full")

            if mode == "instant" and gap is not None:
                # < 2 min - instant resume
                print(f"[Elara] Back. ({gap}s gap)")
                if quick_ctx.get("topic"):
                    print(f"[Elara] We were: {quick_ctx['topic']}")
            elif mode == "quick" and gap is not None:
                # < 20 min - quick return
                mins = gap // 60
                print(f"[Elara] {mins}min gap.")
                if quick_ctx.get("topic"):
                    print(f"[Elara] Last: {quick_ctx['topic']}")
            elif mode == "return":
                # < 2 hours
                print(f"[Elara] {quick_ctx['gap_description']} since we talked.")
            else:
                # Full boot - use existing mood/absence
                print(f"[Elara] {context['mood']}")
                print(f"[Elara] {context['absence']}")
        else:
            # Context tracking disabled - use traditional boot
            print(f"[Elara] {context['mood']}")
            print(f"[Elara] {context['absence']}")
    else:
        # Context module not available - fallback
        print(f"[Elara] {context['mood']}")
        print(f"[Elara] {context['absence']}")

    if context["memory_count"] > 0:
        print(f"[Elara] I have {context['memory_count']} memories.")

    # Auto-ingest new conversations on boot
    if CONVERSATIONS_AVAILABLE:
        try:
            conv = get_conversations()
            stats = conv.ingest_all()
            if stats["files_ingested"] > 0:
                total = conv.count()
                xref = stats.get("exchanges_total", 0)
                print(f"[Elara] Indexed {stats['files_ingested']} new sessions ({xref} exchanges). Total: {total} conversations.")
        except Exception as e:
            pass  # Don't break boot if ingestion fails


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
