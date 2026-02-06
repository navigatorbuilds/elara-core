"""
Elara Overwatch Injector — Format search results into context injections.

Takes ChromaDB search results and formats them into concise, natural
context that gets prepended to the user's message via a hook.
"""

from datetime import datetime
from typing import List, Dict, Any


def _humanize_age(epoch: float) -> str:
    """Convert epoch to human-readable age string."""
    if epoch <= 0:
        return "unknown time ago"

    now = datetime.now().timestamp()
    age_seconds = max(0, now - epoch)
    age_minutes = age_seconds / 60
    age_hours = age_minutes / 60
    age_days = age_hours / 24

    if age_days >= 30:
        months = int(age_days / 30)
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif age_days >= 7:
        weeks = int(age_days / 7)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif age_days >= 2:
        return f"{int(age_days)} days ago"
    elif age_days >= 1:
        return "yesterday"
    elif age_hours >= 2:
        return f"{int(age_hours)} hours ago"
    elif age_hours >= 1:
        return "1 hour ago"
    else:
        return f"{int(age_minutes)} min ago"


def _extract_user_quote(content: str, max_len: int = 120) -> str:
    """Extract the user's part from a conversation exchange."""
    if "User:" in content:
        parts = content.split("User:", 1)
        if len(parts) > 1:
            user_part = parts[1].split("\n\nElara:", 1)[0].strip()
            if len(user_part) > max_len:
                user_part = user_part[:max_len - 3] + "..."
            return user_part
    return ""


def _extract_assistant_summary(content: str, max_len: int = 100) -> str:
    """Extract a brief summary of the assistant's response."""
    if "Elara:" in content:
        parts = content.split("Elara:", 1)
        if len(parts) > 1:
            elara_part = parts[1].strip()
            # Take first sentence or first max_len chars
            first_sentence = elara_part.split(". ")[0]
            if len(first_sentence) > max_len:
                first_sentence = first_sentence[:max_len - 3] + "..."
            return first_sentence
    return ""


def format_injection(results: List[Dict[str, Any]]) -> str:
    """Format cross-reference search results into inject content."""
    if not results:
        return ""

    lines = ["<overwatch-context>"]
    lines.append("Cross-references from past conversations:")

    for r in results[:3]:
        age = _humanize_age(r.get("epoch", 0))
        date = r.get("date", "")
        score = r.get("score", 0)

        user_quote = _extract_user_quote(r.get("content", ""))
        assistant_summary = _extract_assistant_summary(r.get("content", ""))

        lines.append(f"- {age} ({date}):")
        if user_quote:
            lines.append(f'  He said: "{user_quote}"')
        if assistant_summary:
            lines.append(f"  Context: {assistant_summary}")

    lines.append("</overwatch-context>")
    return "\n".join(lines)


def format_event_injection(event_results: List[Dict[str, Any]]) -> str:
    """Format event-triggered search results."""
    if not event_results:
        return ""

    # Group by event type
    by_event = {}
    for r in event_results:
        event_type = r.get("_event", "unknown")
        if event_type not in by_event:
            by_event[event_type] = []
        by_event[event_type].append(r)

    lines = ["<overwatch-event>"]

    if "task_complete" in by_event:
        lines.append("Related to what was just completed:")
        for r in by_event["task_complete"][:2]:
            age = _humanize_age(r.get("epoch", 0))
            user_quote = _extract_user_quote(r.get("content", ""))
            if user_quote:
                lines.append(f'- {age}: "{user_quote}"')

    if "winding_down" in by_event:
        lines.append("From past sessions (possibly unfulfilled):")
        for r in by_event["winding_down"][:3]:
            age = _humanize_age(r.get("epoch", 0))
            user_quote = _extract_user_quote(r.get("content", ""))
            if user_quote:
                lines.append(f'- {age}: "{user_quote}"')

    lines.append("</overwatch-event>")
    return "\n".join(lines)
