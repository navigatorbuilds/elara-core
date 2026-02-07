"""
Elara Boot Priority Engine

Reads handoff.json at boot, applies heuristic rules, outputs a priority brief.
No LLM calls. No API calls. Pure Python judgment.

Rules:
- carried 3+ sessions = OVERDUE (surface loudly)
- promises = ALWAYS surface, ESCALATE with age (100 + carry*5, cap 150)
- reminders = ALWAYS surface
- carry velocity: effective_carry = raw_carry * (1 - days_since_first_seen/90)
- time-of-day filtering (late night = deprioritize work tasks)
- mood_and_mode = set tone for greeting
- writes session state for Overwatch integration
"""

import logging
import json
from pathlib import Path
from datetime import datetime

from core.paths import get_paths
from daemon.handoff import load_handoff, HANDOFF_PATH
from daemon.schemas import atomic_write_json

logger = logging.getLogger("elara.priority")

SESSION_STATE_PATH = get_paths().session_state

# Priority thresholds
OVERDUE_THRESHOLD = 3      # carried N+ sessions = overdue
STALE_THRESHOLD = 2        # carried N+ = stale but not urgent
CARRY_VELOCITY_HORIZON = 90  # days before carry count fully decays
LATE_NIGHT_START = 22      # 10 PM
LATE_NIGHT_END = 6         # 6 AM
MORNING_END = 12           # noon


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
        "firebase", "flutter", "python",
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


def _effective_carry(item: dict) -> float:
    """
    Apply carry velocity decay: items that have been around for months
    gradually lose urgency. effective_carry = raw * (1 - days/90).
    Without first_seen, falls back to raw carry count.
    """
    carried = item.get("carried", 0)
    first_seen = item.get("first_seen", "")

    if not first_seen or carried <= 0:
        return float(carried)

    try:
        first_dt = datetime.fromisoformat(first_seen)
        days_old = (datetime.now() - first_dt).days
        velocity_decay = max(0.3, 1.0 - days_old / CARRY_VELOCITY_HORIZON)
        return carried * velocity_decay
    except (ValueError, TypeError):
        return float(carried)


def _expiry_info(item: dict) -> dict:
    """Check if item has an expiry and compute time remaining."""
    expires = item.get("expires")
    if not expires:
        return {"has_expiry": False}

    try:
        expires_dt = datetime.fromisoformat(expires)
        now = datetime.now()
        remaining = expires_dt - now
        hours_left = remaining.total_seconds() / 3600

        if hours_left < 0:
            days_ago = abs(remaining.days)
            return {"has_expiry": True, "expired": True, "hours_left": hours_left, "label": f"{days_ago}d ago"}
        elif hours_left < 24:
            return {"has_expiry": True, "expired": False, "hours_left": hours_left, "label": f"{hours_left:.0f}h left"}
        elif hours_left < 72:
            days = hours_left / 24
            return {"has_expiry": True, "expired": False, "hours_left": hours_left, "label": f"{days:.0f}d left"}
        else:
            days = hours_left / 24
            return {"has_expiry": True, "expired": False, "hours_left": hours_left, "label": f"{days:.0f}d left"}
    except (ValueError, TypeError):
        return {"has_expiry": False}


def compute_priority(item: dict, time_class: str) -> dict:
    """Score a single item. Returns enriched item with priority info."""
    text = item.get("text", "")
    carried = item.get("carried", 0)
    eff_carry = _effective_carry(item)

    # Base priority from effective carry count (velocity-adjusted)
    if eff_carry >= OVERDUE_THRESHOLD:
        urgency = "OVERDUE"
        score = 90 + eff_carry
    elif eff_carry >= STALE_THRESHOLD:
        urgency = "stale"
        score = 60 + eff_carry * 5
    elif eff_carry > 0:
        urgency = "pending"
        score = 40 + eff_carry * 5
    else:
        urgency = "fresh"
        score = 30

    # Expiry — use max(expiry_score, carry_score), not additive
    exp = _expiry_info(item)
    expiry_label = None
    has_hard_deadline = False
    if exp["has_expiry"]:
        if exp.get("expired"):
            urgency = "EXPIRED"
            score = max(score, 120)
            expiry_label = exp["label"]
            has_hard_deadline = True
        elif exp["hours_left"] < 24:
            urgency = "URGENT"
            score = max(score, 90 + 30)  # at least 120, or carry score if higher
            expiry_label = exp["label"]
            has_hard_deadline = True
        elif exp["hours_left"] < 72:
            score = max(score, 75)  # at least 75, or carry score if higher
            expiry_label = exp["label"]

    # Time-of-day adjustments — EXPIRED/URGENT bypass this entirely
    work = is_work_item(text)
    personal = is_personal_item(text)

    if not has_hard_deadline:
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

    result = {
        "text": text,
        "carried": carried,
        "urgency": urgency,
        "score": score,
        "is_work": work,
        "is_personal": personal,
    }
    if expiry_label:
        result["expiry_label"] = expiry_label
    return result


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

    # Promises ESCALATE with age — social contracts get louder, not quieter
    promises = []
    for item in handoff.get("promises", []):
        if isinstance(item, str):
            text = item
            carried = 0
        else:
            text = item.get("text", str(item))
            carried = item.get("carried", 0)
        score = min(150, 100 + carried * 5)
        promises.append({"text": text, "carried": carried, "urgency": "PROMISE", "score": score})

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

    # Split into overdue/expired vs rest
    overdue = [i for i in all_items if i["urgency"] in ("OVERDUE", "EXPIRED")]
    rest = [i for i in all_items if i["urgency"] not in ("OVERDUE", "EXPIRED")]

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

    # EXPIRED — missed deadlines
    expired = [i for i in overdue if i.get("urgency") == "EXPIRED"]
    urgent = [i for i in top_items if i.get("urgency") == "URGENT"]
    non_expired_overdue = [i for i in overdue if i.get("urgency") != "EXPIRED"]

    if expired:
        lines.append("[Priority] ⚠ EXPIRED:")
        for item in expired:
            lines.append(f"[Priority]   → {item['text']} ({item.get('expiry_label', 'expired')})")

    if urgent:
        lines.append("[Priority] ⏰ EXPIRING SOON:")
        for item in urgent:
            lines.append(f"[Priority]   → {item['text']} ({item.get('expiry_label', '<24h')})")

    # OVERDUE — these MUST be mentioned in greeting
    if non_expired_overdue:
        lines.append("[Priority] ⚠ OVERDUE:")
        for item in non_expired_overdue:
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


def _write_session_state(brief: dict):
    """
    Write session state for Overwatch integration.
    Priority engine is the source of truth for 'what matters right now'.
    Overwatch reads this to boost relevant search results and replace
    hardcoded winding-down queries with actual overdue items.
    """
    state = {
        "overdue_items": [i["text"] for i in brief["overdue"]],
        "promises": [i["text"] for i in brief["promises"]],
        "reminders": [i["text"] for i in brief["reminders"]],
        "session_start": datetime.now().isoformat(),
        "session_number": brief["session_number"],
        "injected_topics": [],
    }
    try:
        atomic_write_json(SESSION_STATE_PATH, state)
    except OSError:
        pass


def boot_priority() -> str | None:
    """
    Main entry point. Called from boot.py.
    Returns formatted brief text, or None if no handoff exists.
    Also writes session state for Overwatch.
    """
    handoff = load_handoff()
    if handoff is None:
        return None

    brief = generate_brief(handoff)
    _write_session_state(brief)
    return brief["brief_text"]


if __name__ == "__main__":
    # Test standalone
    result = boot_priority()
    if result:
        print(result)
    else:
        print("[Priority] No handoff file found.")
