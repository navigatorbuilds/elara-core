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

try:
    from daemon.corrections import ensure_index as corrections_ensure_index
    CORRECTIONS_INDEX_AVAILABLE = True
except ImportError:
    CORRECTIONS_INDEX_AVAILABLE = False


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

        # Recall user's plans and intentions from recent conversations
        try:
            _surface_intentions(conv)
        except Exception:
            pass  # Don't break boot if recall fails


def _surface_handoff():
    """Read the session handoff file written on previous goodbye.
    This is the primary short-term memory between sessions."""
    handoff_path = Path.home() / ".claude" / "elara-handoff.json"
    if not handoff_path.exists():
        return False

    try:
        data = json.loads(handoff_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    # Check it's recent (< 24h)
    ts = data.get("timestamp", "")
    if ts:
        try:
            written = datetime.fromisoformat(ts)
            age_hours = (datetime.now() - written).total_seconds() / 3600
            if age_hours > 24:
                return False
        except ValueError:
            pass

    has_content = False

    def _format_item(item):
        """Format a handoff item — supports both string and dict with carry count."""
        if isinstance(item, dict):
            text = item.get("text", "")
            carried = item.get("carried", 0)
            if carried >= 3:
                return f"{text} [OVERDUE — {carried} sessions!]"
            elif carried > 0:
                return f"{text} (carried {carried}x)"
            return text
        return str(item)

    plans = data.get("next_plans", [])
    if plans:
        has_content = True
        print("[Elara] His plans:")
        for p in plans:
            print(f"[Elara]   > {_format_item(p)}")

    reminders = data.get("reminders", [])
    if reminders:
        has_content = True
        print("[Elara] Reminders:")
        for r in reminders:
            print(f"[Elara]   > {_format_item(r)}")

    mood = data.get("mood_and_mode", "")
    if mood:
        has_content = True
        print(f"[Elara] Mood/mode: {mood}")

    promises = data.get("promises", [])
    if promises:
        has_content = True
        print("[Elara] Promises:")
        for p in promises:
            print(f"[Elara]   > {_format_item(p)}")

    unfinished = data.get("unfinished", [])
    if unfinished:
        has_content = True
        print("[Elara] Unfinished:")
        for u in unfinished:
            print(f"[Elara]   > {_format_item(u)}")

    return has_content


def _surface_intentions(conv):
    """Surface user's recent context. Handoff file first, last messages as fallback."""

    # Primary: structured handoff from previous session
    if _surface_handoff():
        return

    # Fallback: raw last messages from previous session
    lines = []
    try:
        lines.extend(_last_session_messages())
    except Exception:
        pass

    if lines:
        print("[Elara] Last things he said (previous session):")
        for line in lines:
            print(f"[Elara]   > \"{line}\"")


def _last_session_messages():
    """Read last 5 user messages from the most recent completed session."""
    session_dir = Path.home() / ".claude" / "projects" / "-home-neboo"
    if not session_dir.exists():
        return []

    # Find the 2nd most recent .jsonl (current session is the newest, skip it)
    jsonl_files = sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if len(jsonl_files) < 2:
        return []

    prev_session = jsonl_files[1]  # Previous session (not current)

    # Check it's recent (< 24h)
    age_hours = (datetime.now().timestamp() - prev_session.stat().st_mtime) / 3600
    if age_hours > 24:
        return []

    # Read last user messages
    user_messages = []
    with open(prev_session) as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("type") == "user":
                    msg = obj.get("message", {})
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if isinstance(content, str) and len(content.strip()) > 5:
                        text = content.strip()
                        # Skip system/task messages
                        if text.startswith("<") or text.startswith("{"):
                            continue
                        if len(text) > 150:
                            text = text[:147] + "..."
                        user_messages.append(text)
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                t = item.get("text", "").strip()
                                if len(t) > 5:
                                    if len(t) > 150:
                                        t = t[:147] + "..."
                                    user_messages.append(t)
            except (json.JSONDecodeError, KeyError):
                continue

    # Return last 5 user messages (that's where plans live)
    return user_messages[-5:] if user_messages else []


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
