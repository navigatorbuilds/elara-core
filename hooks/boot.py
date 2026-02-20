#!/usr/bin/env python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Boot Hook
Run this at the start of each Claude Code session.
Outputs context that can be injected into the prompt.
"""

import json
from pathlib import Path
from datetime import datetime

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

try:
    from daemon.corrections import ensure_index as corrections_ensure_index
    CORRECTIONS_INDEX_AVAILABLE = True
except ImportError:
    CORRECTIONS_INDEX_AVAILABLE = False

try:
    from daemon.priority import boot_priority
    PRIORITY_AVAILABLE = True
except ImportError:
    PRIORITY_AVAILABLE = False

try:
    from daemon.business import boot_summary as business_boot_summary
    BUSINESS_AVAILABLE = True
except ImportError:
    BUSINESS_AVAILABLE = False

try:
    from daemon.briefing import boot_summary as briefing_boot_summary
    BRIEFING_AVAILABLE = True
except ImportError:
    BRIEFING_AVAILABLE = False

try:
    from memory.temporal import boot_temporal_context
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False


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

    # Sync corrections index on boot
    if CORRECTIONS_INDEX_AVAILABLE:
        try:
            corrections_ensure_index()
        except Exception:
            pass

    # Auto-ingest new conversations on boot
    if CONVERSATIONS_AVAILABLE:
        try:
            conv = get_conversations()
            stats = conv.ingest_all()
            if stats["files_ingested"] > 0:
                total = conv.count()
                xref = stats.get("exchanges_total", 0)
                print(f"[Elara] Indexed {stats['files_ingested']} new sessions ({xref} exchanges). Total: {total} conversations.")
        except Exception:
            pass  # Don't break boot if ingestion fails

    # Long-range memory — surface old important memories + landmarks
    if TEMPORAL_AVAILABLE:
        try:
            temporal_ctx = boot_temporal_context()
            if temporal_ctx:
                print(temporal_ctx)
        except Exception:
            pass  # Don't break boot if temporal sweep fails

    # Priority brief — what matters right now
    if PRIORITY_AVAILABLE:
        try:
            brief = boot_priority()
            if brief:
                print(brief)
        except Exception:
            pass  # Don't break boot if priority engine fails

    # Business summary — active ideas, stale ideas
    if BUSINESS_AVAILABLE:
        try:
            biz = business_boot_summary()
            if biz:
                print(biz)
        except Exception:
            pass

    # Daily briefing — RSS feed highlights
    if BRIEFING_AVAILABLE:
        try:
            brief = briefing_boot_summary()
            if brief:
                print(brief)
        except Exception:
            pass

    # Session snapshot — continuity between sessions
    _show_snapshot(quick_ctx.get("gap_seconds") if CONTEXT_AVAILABLE and quick_ctx else None)

    # Start Overwatch daemon if not already running
    _start_overwatch()


from core.paths import get_paths
SNAPSHOT_PATH = get_paths().session_snapshot


def _show_snapshot(gap_seconds=None):
    """Show session snapshot for continuity.

    Quick reboot (<30 min): show continuation (what we were just doing)
    Fresh session (>30 min): show greeting_hint (summary of last session)
    """
    if not SNAPSHOT_PATH.exists():
        return

    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return

    if gap_seconds is not None and gap_seconds < 1800:
        # Quick reboot — show continuation + raw exchanges
        continuation = snapshot.get("continuation", "")
        if continuation:
            print(f"[Snapshot] {continuation}")
        # Show raw exchanges so next-me can actually execute, not just know the topic
        exchanges = snapshot.get("last_exchanges", [])
        if exchanges:
            print(f"[Snapshot] Last {len(exchanges)} exchanges (raw):")
            for ex in exchanges[-3:]:  # Last 3 most relevant
                user_text = ex.get("user", "")[:120]
                assistant_text = ex.get("assistant", "")[:120]
                if user_text:
                    print(f"  User: {user_text}")
                if assistant_text:
                    print(f"  Elara: {assistant_text}")
    else:
        # Fresh session — show greeting hint
        hint = snapshot.get("greeting_hint", "")
        if hint:
            print(f"[Snapshot] Last session: {hint}")


def _start_overwatch():
    """Start the Overwatch daemon if not already running."""
    import subprocess
    script = Path(__file__).parent.parent / "scripts" / "overwatch-start.sh"
    if script.exists():
        try:
            result = subprocess.run(
                [str(script)],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                print(result.stdout.strip())
        except Exception:
            pass  # Don't break boot if Overwatch fails to start


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
