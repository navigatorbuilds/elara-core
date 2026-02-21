# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Unified Decision Registry tool — 8 actions for managing crystallized judgments.

Prevents repeating failed decisions across sessions. O(1) in-memory fast-check
with SQLite-backed persistence and automatic feeds from corrections/outcomes.
"""

from typing import Optional
from elara_mcp._app import tool
from daemon.udr import get_registry


@tool()
def elara_udr(
    action: str = "stats",
    domain: Optional[str] = None,
    entity: Optional[str] = None,
    verdict: str = "rejected",
    reason: str = "",
    confidence: float = 0.8,
    source: str = "manual",
    session: Optional[int] = None,
    tags: Optional[str] = None,
    n: int = 20,
) -> str:
    """
    Unified Decision Registry — crystallized judgments that prevent repetition.

    Args:
        action: What to do:
            "record"   — Record a decision (needs domain, entity)
            "check"    — Check if a decision exists (needs domain, entity)
            "scan"     — Scan text for known rejected entities (needs reason as text)
            "list"     — List decisions (optional domain, verdict filters)
            "review"   — Full details for one decision (needs domain, entity)
            "stats"    — Aggregate statistics
            "boot"     — Load entity set into memory, show summary
            "backfill" — Backfill from existing corrections and outcomes
        domain: Decision domain (upload, outreach, architecture, tool, etc.)
        entity: The specific thing (arxiv, esa, redis, etc.)
        verdict: rejected, failed, approved, revisit (default: rejected)
        reason: Why this verdict was reached
        confidence: 0-1 confidence level (default: 0.8)
        source: Where this came from (manual, correction, outcome)
        session: Session number when recorded
        tags: Comma-separated tags
        n: Number of results for list (default 20)

    Returns:
        Decision info, list, stats, or operation result
    """
    reg = get_registry()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    if action == "record":
        if not domain or not entity:
            return "Error: 'record' requires domain and entity."
        result = reg.record_decision(
            domain=domain,
            entity=entity,
            verdict=verdict,
            reason=reason,
            confidence=confidence,
            source=source,
            session=session,
            tags=tag_list,
        )
        return (
            f"Recorded: {result['action_signature']} [{result['verdict']}]\n"
            f"Confidence: {result['confidence']}\n"
            f"Reason: {result['reason'][:100]}"
        )

    elif action == "check":
        if not domain or not entity:
            return "Error: 'check' requires domain and entity."
        result = reg.check_decision(domain, entity)
        if result:
            return (
                f"FOUND: {result['action_signature']}\n"
                f"Verdict: {result['verdict']} (confidence: {result['confidence']})\n"
                f"Reason: {result['reason']}\n"
                f"Source: {result['source']} | Created: {result['created'][:10]}\n"
                f"Updated: {result['updated'][:10]}"
            )
        return f"No decision found for {domain}:{entity}"

    elif action == "scan":
        text = reason  # Reuse reason param as text input
        if not text:
            return "Error: 'scan' requires text in the reason parameter."
        matches = reg.check_entities(text)
        if not matches:
            return "No known rejected entities found in text."
        lines = [f"Found {len(matches)} decision(s):"]
        for m in matches:
            lines.append(
                f"  - {m['domain']}:{m['entity']} [{m['verdict']}] — {m['reason'][:60]}"
            )
        return "\n".join(lines)

    elif action == "list":
        results = reg.list_decisions(domain=domain, verdict=verdict, n=n)
        if not results:
            return "No decisions found."
        lines = [f"{len(results)} decision(s):"]
        for r in results:
            lines.append(
                f"  {r['action_signature']} [{r['verdict']}] "
                f"conf={r['confidence']} src={r['source']} "
                f"({r['updated'][:10]})"
            )
        return "\n".join(lines)

    elif action == "review":
        if not domain or not entity:
            return "Error: 'review' requires domain and entity."
        result = reg.review_decision(domain, entity)
        if not result:
            return f"No decision found for {domain}:{entity}"
        lines = [
            f"Decision: {result['action_signature']}",
            f"Domain: {result['domain']}",
            f"Entity: {result['entity']}",
            f"Verdict: {result['verdict']}",
            f"Confidence: {result['confidence']}",
            f"Reason: {result['reason']}",
            f"Source: {result['source']}",
            f"Created: {result['created']}",
            f"Updated: {result['updated']}",
            f"Tags: {', '.join(result.get('tags', []))}",
        ]
        return "\n".join(lines)

    elif action == "stats":
        s = reg.stats()
        lines = [
            f"Total decisions: {s['total_decisions']}",
            f"In-memory set: {s['entity_set_size']} entities",
            f"Avg confidence: {s['avg_confidence']}",
            "",
            "By verdict:",
        ]
        for v, c in s["by_verdict"].items():
            lines.append(f"  {v}: {c}")
        lines.append("\nBy domain:")
        for d, c in s["by_domain"].items():
            lines.append(f"  {d}: {c}")
        lines.append("\nBy source:")
        for src, c in s["by_source"].items():
            lines.append(f"  {src}: {c}")
        return "\n".join(lines)

    elif action == "boot":
        return reg.boot_decisions()

    elif action == "backfill":
        c_count = reg.backfill_from_corrections()
        o_count = reg.backfill_from_outcomes()
        return (
            f"Backfill complete.\n"
            f"  From corrections: {c_count}\n"
            f"  From outcomes: {o_count}\n"
            f"  Total in registry: {reg.stats()['total_decisions']}"
        )

    else:
        return (
            f"Unknown action '{action}'. "
            "Valid: record, check, scan, list, review, stats, boot, backfill"
        )
