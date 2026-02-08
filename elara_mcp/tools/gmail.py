# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Gmail tools: read, triage, send, archive, search, sync.

1 tool, dispatch via action parameter (consistent with other modules).
"""

from typing import Optional
from elara_mcp._app import mcp


@mcp.tool()
def elara_gmail(
    action: str = "inbox",
    message_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    query: Optional[str] = None,
    label: Optional[str] = None,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    reply_to: Optional[str] = None,
    add_labels: Optional[str] = None,
    remove_labels: Optional[str] = None,
    n: int = 10,
) -> str:
    """
    Gmail management — read, triage, send, archive, search emails.

    Args:
        action: What to do:
            "auth"      — Run OAuth2 flow (opens browser)
            "labels"    — List all Gmail labels
            "inbox"     — Fetch recent inbox messages
            "search"    — Search by Gmail query OR semantic search
            "read"      — Get full message or thread
            "triage"    — Classify unread messages by urgency
            "summarize" — Bullet-point summary of recent mail
            "send"      — Compose and send an email
            "archive"   — Archive message(s)
            "label"     — Apply/remove labels on a message
            "trash"     — Move message to trash
            "sync"      — Index new messages into ChromaDB
            "stats"     — Sync state, indexed count
        message_id: Gmail message ID (for read, archive, label, trash)
        thread_id: Gmail thread ID (for read)
        query: Search query (Gmail syntax for search, natural language for semantic)
        label: Label ID to filter by (for inbox)
        to: Recipient email (for send)
        subject: Email subject (for send)
        body: Email body (for send)
        reply_to: Thread ID to reply to (for send)
        add_labels: Comma-separated label IDs to add (for label)
        remove_labels: Comma-separated label IDs to remove (for label)
        n: Number of results (default 10)

    Returns:
        Email data, triage results, or operation status
    """
    from daemon.gmail import (
        authorize, is_authorized, list_labels,
        fetch_messages, get_message, get_thread,
        send_message, modify_message, trash_message,
        triage_inbox, summarize_inbox,
        search_messages, sync, get_sync_stats,
    )

    if action == "auth":
        result = authorize()
        return f"{result['status'].upper()}: {result['message']}"

    # All other actions require auth
    if action != "auth" and not is_authorized():
        return "Not authorized. Run action='auth' first to connect Gmail."

    if action == "labels":
        labels = list_labels()
        if not labels:
            return "No labels found (or API error)."
        lines = [f"{len(labels)} labels:"]
        for lb in labels:
            lines.append(f"  {lb['name']} ({lb['id']})")
        return "\n".join(lines)

    if action == "inbox":
        messages = fetch_messages(query=query or "", label=label, max_results=n)
        if not messages:
            return "Inbox empty (or no matches)."
        lines = [f"{len(messages)} messages:"]
        for msg in messages:
            unread = " *" if msg.get("is_unread") else ""
            lines.append(f"  [{msg['id'][:8]}]{unread} {msg['from'][:35]}")
            lines.append(f"    {msg['subject'][:60]}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required for search."
        # Try semantic search first, fall back to Gmail query
        semantic = search_messages(query, n=n)
        if semantic:
            lines = [f"Semantic search ({len(semantic)} results):"]
            for item in semantic:
                lines.append(f"  [{item['score']:.2f}] {item['from'][:30]}: {item['subject'][:50]}")
                lines.append(f"    ID: {item['id']} | {item['date']}")
            return "\n".join(lines)
        # Fallback to Gmail native search
        messages = fetch_messages(query=query, max_results=n)
        if not messages:
            return "No results found."
        lines = [f"Gmail search ({len(messages)} results):"]
        for msg in messages:
            lines.append(f"  [{msg['id'][:8]}] {msg['from'][:30]}: {msg['subject'][:50]}")
        return "\n".join(lines)

    if action == "read":
        if thread_id:
            thread = get_thread(thread_id)
            if not thread:
                return f"Thread {thread_id} not found."
            lines = [f"Thread: {thread['message_count']} messages"]
            for msg in thread["messages"]:
                lines.append(f"  [{msg['id'][:8]}] {msg['from'][:30]}: {msg['subject'][:50]}")
                lines.append(f"    {msg['snippet'][:80]}")
            return "\n".join(lines)

        if message_id:
            msg = get_message(message_id)
            if not msg:
                return f"Message {message_id} not found."
            body_preview = (msg.get("body") or "")[:2000]
            lines = [
                f"From: {msg['from']}",
                f"To: {msg['to']}",
                f"Subject: {msg['subject']}",
                f"Date: {msg['date']}",
                f"Labels: {', '.join(msg.get('labels', []))}",
                f"---",
                body_preview,
            ]
            return "\n".join(lines)

        return "Error: message_id or thread_id required for read."

    if action == "triage":
        triaged = triage_inbox(max_results=n)
        if not triaged:
            return "No unread messages to triage."
        # Group by category
        by_cat: dict = {}
        for msg in triaged:
            cat = msg.get("category", "informational")
            by_cat.setdefault(cat, []).append(msg)

        lines = [f"Triaged {len(triaged)} unread messages:"]
        for cat in ["urgent", "action-needed", "informational", "newsletter", "spam"]:
            msgs = by_cat.get(cat, [])
            if msgs:
                lines.append(f"\n  [{cat.upper()}] ({len(msgs)})")
                for msg in msgs:
                    lines.append(f"    {msg['from'][:30]}: {msg['subject'][:50]}")
        return "\n".join(lines)

    if action == "summarize":
        summary = summarize_inbox(max_results=n)
        return summary

    if action == "send":
        if not to or not subject:
            return "Error: to and subject are required."
        result = send_message(to=to, subject=subject, body=body or "", reply_to=reply_to)
        if result["status"] == "ok":
            return f"Sent to {to} (ID: {result.get('message_id', '?')[:8]})"
        return f"Error: {result.get('message', 'unknown')}"

    if action == "archive":
        if not message_id:
            return "Error: message_id is required."
        result = modify_message(message_id, remove_labels=["INBOX"])
        if result["status"] == "ok":
            return f"Archived {message_id[:8]}"
        return f"Error: {result.get('message', 'unknown')}"

    if action == "label":
        if not message_id:
            return "Error: message_id is required."
        add = [l.strip() for l in add_labels.split(",")] if add_labels else None
        remove = [l.strip() for l in remove_labels.split(",")] if remove_labels else None
        if not add and not remove:
            return "Error: add_labels or remove_labels required."
        result = modify_message(message_id, add_labels=add, remove_labels=remove)
        if result["status"] == "ok":
            parts = []
            if add:
                parts.append(f"added: {', '.join(add)}")
            if remove:
                parts.append(f"removed: {', '.join(remove)}")
            return f"Labels updated on {message_id[:8]} ({'; '.join(parts)})"
        return f"Error: {result.get('message', 'unknown')}"

    if action == "trash":
        if not message_id:
            return "Error: message_id is required."
        result = trash_message(message_id)
        if result["status"] == "ok":
            return f"Trashed {message_id[:8]}"
        return f"Error: {result.get('message', 'unknown')}"

    if action == "sync":
        result = sync(max_results=n)
        return (
            f"Sync complete: {result.get('fetched', 0)} fetched, "
            f"{result.get('new_indexed', 0)} newly indexed, "
            f"{result.get('total_indexed', 0)} total in DB"
        )

    if action == "stats":
        stats = get_sync_stats()
        lines = [
            f"Authorized: {stats['authorized']}",
            f"Last sync: {stats.get('last_sync') or 'never'}",
            f"Indexed messages: {stats.get('indexed_count', 0)}",
        ]
        return "\n".join(lines)

    return (
        f"Unknown action: {action}. "
        "Use: auth, labels, inbox, search, read, triage, summarize, "
        "send, archive, label, trash, sync, stats"
    )
