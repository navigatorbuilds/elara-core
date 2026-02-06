"""
Elara Boot Priority Engine

Reads handoff.json at boot, applies heuristic rules, outputs a priority brief.
No LLM calls. No API calls. Pure Python judgment.

Rules:
- carried 3+ sessions = OVERDUE (surface loudly)
- promises = ALWAYS surface (no exceptions)
- reminders = ALWAYS surface
- time-of-day filtering (late night = deprioritize work tasks)
- mood_and_mode = set tone for greeting
"""

import json
from pathlib import Path
from datetime import datetime

HANDOFF_PATH = Path.home() / ".claude" / "elara-handoff.json"

# Priority thresholds
OVERDUE_THRESHOLD = 3      # carried N+ sessions = overdue
STALE_THRESHOLD = 2        # carried N+ = stale but not urgent
LATE_NIGHT_START = 22      # 10 PM
LATE_NIGHT_END = 6         # 6 AM
MORNING_END = 12           # noon


def load_handoff() -> dict | None:
    """Load the handoff file. Returns None if missing or broken."""
    if not HANDOFF_PATH.exists():
        return None
    try:
        return json.loads(HANDOFF_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def classify_time(hour: int) -> str:
    """Classify current time of day."""
    if LATE_NIGHT_START <= hour or hour < LATE_NIGHT_END:
        return "late_night"
    elif hour < MORNING_END:
        return "morning"
    elif hour < 18:
        return "afternoon"
    else:
        return "evening"


def is_work_item(text: str) -> bool:
    """Heuristic: does this look like a work/dev task?"""
    work_signals = [
        "cleanup", "refactor", "build", "fix", "deploy", "test",
        "phase", "v1", "v2", "audit", "ship", "commit", "push",
        "firebase", "flutter", "python", "planpulse", "handybill",
        "elara-core", "overwatch", "chromadb", "scoring", "priority",
        "bug", "feature", "implement", "migration"
    ]
    lower = text.lower()
    return any(signal in lower for signal in work_signals)


def is_personal_item(text: str) -> bool:
    """Heuristic: is this personal/emotional/drift?"""
    personal_signals = [
        "drift", "companion", "therapist", "relax", "talk",
        "mood", "feeling", "personal", "kimi", "medium"
    ]
    lower = text.lower()
    return any(signal in lower for signal in personal_signals)


def compute_priority(item: dict, time_class: str) -> dict:
    """Score a single item. Returns enriched item with priority info."""
    text = item.get("text", "")
    carried = item.get("carried", 0)

    # Base priority from carry count
    if carried >= OVERDUE_THRESHOLD:
        urgency = "OVERDUE"
        score = 90 + carried  # higher the longer it's carried
    elif carried >= STALE_THRESHOLD:
        urgency = "stale"
        score = 60 + carried * 5
    elif carried > 0:
        urgency = "pending"
        score = 40 + carried * 5
    else:
        urgency = "fresh"
        score = 30

    # Time-of-day adjustments
    work = is_work_item(text)
    personal = is_personal_item(text)

    if time_class == "late_night":
        if work:
            score -= 20  # deprioritize work late at night
        if personal:
            score += 15  # boost personal/drift
    elif time_class == "morning":
        if work:
            score += 10  # morning = good for work
        if personal:
            score -= 5
    elif time_class == "afternoon":
        if work:
            score += 5

    return {
        "text": text,
        "carried": carried,
        "urgency": urgency,
        "score": score,
        "is_work": work,
        "is_personal": personal,
    }


def generate_brief(handoff: dict, now: datetime = None) -> dict:
    """
    Generate the priority brief from handoff data.

    Returns:
        {
            "time_class": "late_night" | "morning" | ...,
            "mood": str,
            "overdue": [items],     # carried 3+, MUST surface
            "promises": [items],    # ALWAYS surface
            "reminders": [items],   # ALWAYS surface
            "top_items": [items],   # highest scored non-overdue items
            "suppressed": [items],  # deprioritized by time (still available)
            "session_number": int,
            "brief_text": str,      # formatted output for boot
        }
    """
    if now is None:
        now = datetime.now()

    time_class = classify_time(now.hour)
    session_num = handoff.get("session_number", "?")
    mood = handoff.get("mood_and_mode", "")

    # Collect all items from all categories
    all_items = []

    for item in handoff.get("next_plans", []):
        scored = compute_priority(item, time_class)
        scored["source"] = "plan"
        all_items.append(scored)

    for item in handoff.get("unfinished", []):
        scored = compute_priority(item, time_class)
        scored["source"] = "unfinished"
        all_items.append(scored)

    # Promises and reminders get max priority always
    promises = []
    for item in handoff.get("promises", []):
        text = item if isinstance(item, str) else item.get("text", str(item))
        promises.append({"text": text, "urgency": "PROMISE", "score": 100})

    reminders = []
    for item in handoff.get("reminders", []):
        scored = compute_priority(item, time_class)
        scored["source"] = "reminder"
        scored["score"] = max(scored["score"], 85)  # reminders always high
        reminders.append(scored)

    # Deduplicate by text similarity (handoff often has same item in plans + unfinished)
    seen_texts = set()
    deduped = []
    for item in all_items:
        # Normalize for comparison: lowercase, strip punctuation
        key = item["text"].lower().strip().rstrip(".")
        # Check if any existing key shares significant overlap
        is_dupe = False
        key_words = set(key.split())
        for seen in seen_texts:
            seen_words = set(seen.split())
            # If 60%+ of words overlap, it's a dupe
            if len(key_words) > 0 and len(seen_words) > 0:
                overlap = len(key_words & seen_words)
                smaller = min(len(key_words), len(seen_words))
                if smaller > 0 and overlap / smaller >= 0.6:
                    is_dupe = True
                    break
            # Also check substring
            if seen in key or key in seen:
                is_dupe = True
                break
        if not is_dupe:
            deduped.append(item)
            seen_texts.add(key)
    all_items = deduped

    # Sort all items by score descending
    all_items.sort(key=lambda x: x["score"], reverse=True)

    # Split into overdue vs rest
    overdue = [i for i in all_items if i["urgency"] == "OVERDUE"]
    rest = [i for i in all_items if i["urgency"] != "OVERDUE"]

    # Top items = highest scored non-overdue (max 3)
    top_items = rest[:3]

    # Suppressed = work items deprioritized by late night (for transparency)
    suppressed = []
    if time_class == "late_night":
        suppressed = [i for i in rest if i["is_work"] and i["score"] < 40]

    # Build the text brief
    brief_text = _format_brief(
        time_class, session_num, mood,
        overdue, promises, reminders, top_items, suppressed
    )

    return {
        "time_class": time_class,
        "mood": mood,
        "overdue": overdue,
        "promises": promises,
        "reminders": reminders,
        "top_items": top_items,
        "suppressed": suppressed,
        "session_number": session_num,
        "brief_text": brief_text,
    }


def _format_brief(
    time_class, session_num, mood,
    overdue, promises, reminders, top_items, suppressed
) -> str:
    """Format the priority brief as text for boot output."""
    lines = []
    lines.append(f"[Priority] Session {session_num + 1} | {time_class.replace('_', ' ')}")

    if mood:
        # Truncate mood to first sentence for brevity
        first_sentence = mood.split(".")[0].strip()
        lines.append(f"[Priority] Last mood: {first_sentence}")

    # OVERDUE — these MUST be mentioned in greeting
    if overdue:
        lines.append("[Priority] ⚠ OVERDUE:")
        for item in overdue:
            lines.append(f"[Priority]   → {item['text']} (carried {item['carried']} sessions)")

    # PROMISES — non-negotiable
    if promises:
        lines.append("[Priority] ⚠ PROMISES:")
        for item in promises:
            lines.append(f"[Priority]   → {item['text']}")

    # REMINDERS — high priority
    if reminders:
        lines.append("[Priority] 📌 REMINDERS:")
        for item in reminders:
            carried_note = f" (carried {item['carried']})" if item.get("carried", 0) > 0 else ""
            lines.append(f"[Priority]   → {item['text']}{carried_note}")

    # TOP items — what's most relevant right now
    if top_items:
        lines.append("[Priority] Next up:")
        for item in top_items:
            tag = f" [{item['urgency']}]" if item["urgency"] != "fresh" else ""
            lines.append(f"[Priority]   - {item['text']}{tag}")

    # Suppressed — mention if any, so I know they exist but aren't priority
    if suppressed:
        lines.append(f"[Priority] ({len(suppressed)} work items deprioritized — late night)")

    return "\n".join(lines)


def boot_priority() -> str | None:
    """
    Main entry point. Called from boot.py.
    Returns formatted brief text, or None if no handoff exists.
    """
    handoff = load_handoff()
    if handoff is None:
        return None

    brief = generate_brief(handoff)
    return brief["brief_text"]


if __name__ == "__main__":
    # Test standalone
    result = boot_priority()
    if result:
        print(result)
    else:
        print("[Priority] No handoff file found.")
