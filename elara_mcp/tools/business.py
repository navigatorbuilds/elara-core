# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Business intelligence tools: idea tracking, competitors, viability scoring.

1 tool, dispatch via action parameter (consistent with other modules).
"""

from typing import Optional
from elara_mcp._app import mcp
from daemon.schemas import ElaraNotFoundError, ElaraValidationError
from daemon.business import (
    create_idea, add_competitor, score_idea, update_idea,
    get_idea, list_ideas, link_to_reasoning, link_to_outcome,
    boot_summary, generate_review, get_idea_stats,
)


@mcp.tool()
def elara_business(
    action: str = "list",
    idea_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    target_audience: Optional[str] = None,
    your_angle: Optional[str] = None,
    competitor_name: Optional[str] = None,
    strengths: Optional[str] = None,
    weaknesses: Optional[str] = None,
    url: Optional[str] = None,
    problem: Optional[int] = None,
    market: Optional[int] = None,
    effort: Optional[int] = None,
    monetization: Optional[int] = None,
    fit: Optional[int] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
    min_score: Optional[int] = None,
    trail_id: Optional[str] = None,
    outcome_id: Optional[str] = None,
) -> str:
    """
    Business intelligence — track ideas, competitors, and viability.

    Args:
        action: What to do:
            "idea"    — Create a new business idea (needs name, description)
            "compete" — Add a competitor (needs idea_id, competitor_name)
            "score"   — Score an idea 1-5 on 5 axes (needs idea_id + all 5 scores)
            "update"  — Update status or add notes (needs idea_id)
            "list"    — List ideas (optional status, min_score filters)
            "review"  — Full report on one idea (needs idea_id)
            "link"    — Link to reasoning trail or outcome (needs idea_id + trail_id or outcome_id)
            "stats"   — Summary statistics
            "boot"    — Boot summary (what's active, what's stale)
        idea_id: Idea identifier (auto-generated from name on create)
        name: Idea name (for create)
        description: What the idea is (for create)
        target_audience: Who it's for
        your_angle: What makes yours different
        competitor_name: Competitor name (for compete)
        strengths: Competitor strengths
        weaknesses: Competitor weaknesses
        url: Competitor URL
        problem: Problem severity 1-5 (for score)
        market: Market size 1-5 (for score)
        effort: Effort required 1-5 (for score, higher = easier)
        monetization: Revenue potential 1-5 (for score)
        fit: Personal fit 1-5 (for score)
        status: exploring/validated/building/launched/abandoned (for update/list filter)
        notes: Note text (for update)
        tags: Comma-separated tags (for create)
        min_score: Minimum total score filter (for list)
        trail_id: Reasoning trail ID (for link)
        outcome_id: Outcome ID (for link)

    Returns:
        Idea info, list, review, or stats
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    if action == "idea":
        if not name or not description:
            return "Error: name and description are required to create an idea."
        try:
            result = create_idea(name, description, target_audience or "", your_angle or "", tag_list)
        except ElaraValidationError as e:
            return str(e)
        lines = [
            f"Idea created: {result['idea_id']}",
            f"Name: {result['name']}",
            f"Status: exploring",
        ]
        if target_audience:
            lines.append(f"Target: {target_audience}")
        if your_angle:
            lines.append(f"Angle: {your_angle}")
        return "\n".join(lines)

    if action == "compete":
        if not idea_id or not competitor_name:
            return "Error: idea_id and competitor_name are required."
        try:
            result = add_competitor(idea_id, competitor_name, strengths or "", weaknesses or "", url or "")
        except ElaraNotFoundError as e:
            return str(e)
        n = len(result["competitors"])
        return f"Competitor '{competitor_name}' added to {idea_id} ({n} total)"

    if action == "score":
        if not idea_id:
            return "Error: idea_id is required."
        if any(v is None for v in [problem, market, effort, monetization, fit]):
            return "Error: all 5 scores required (problem, market, effort, monetization, fit). Each 1-5."
        try:
            result = score_idea(idea_id, problem, market, effort, monetization, fit)
        except ElaraNotFoundError as e:
            return str(e)
        s = result["score"]
        return (
            f"Scored {idea_id}: {s['total']}/25\n"
            f"  Problem: {s['problem']} | Market: {s['market']} | Effort: {s['effort']}\n"
            f"  Monetization: {s['monetization']} | Fit: {s['fit']}"
        )

    if action == "update":
        if not idea_id:
            return "Error: idea_id is required."
        try:
            result = update_idea(idea_id, status=status, notes=notes)
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)
        parts = [f"Updated {idea_id}"]
        if status:
            parts.append(f"status → {status}")
        if notes:
            parts.append(f"note added")
        return " | ".join(parts)

    if action == "list":
        ideas = list_ideas(status=status, min_score=min_score)
        if not ideas:
            return "No ideas found."
        lines = [f"{len(ideas)} idea(s):"]
        for i in ideas:
            score_str = f" ({i['score']['total']}/25)" if i.get("score") else ""
            comp_str = f" [{len(i.get('competitors', []))} competitors]" if i.get("competitors") else ""
            lines.append(f"  [{i['status']}] {i['idea_id']}: {i['name']}{score_str}{comp_str}")
        return "\n".join(lines)

    if action == "review":
        if not idea_id:
            return "Error: idea_id is required."
        review = generate_review(idea_id)
        if not review:
            return f"Idea '{idea_id}' not found."
        return review

    if action == "link":
        if not idea_id:
            return "Error: idea_id is required."
        try:
            if trail_id:
                link_to_reasoning(idea_id, trail_id)
                return f"Linked reasoning trail {trail_id} to {idea_id}"
            if outcome_id:
                link_to_outcome(idea_id, outcome_id)
                return f"Linked outcome {outcome_id} to {idea_id}"
        except ElaraNotFoundError as e:
            return str(e)
        return "Error: provide trail_id or outcome_id to link."

    if action == "stats":
        stats = get_idea_stats()
        if stats["total"] == 0:
            return "No business ideas tracked yet."
        lines = [
            f"Total ideas: {stats['total']}",
            f"Scored: {stats['scored']}",
        ]
        if stats["avg_score"] is not None:
            lines.append(f"Average score: {stats['avg_score']}/25")
        if stats["by_status"]:
            status_str = ", ".join(f"{k}: {v}" for k, v in stats["by_status"].items())
            lines.append(f"By status: {status_str}")
        return "\n".join(lines)

    if action == "boot":
        summary = boot_summary()
        return summary or "No active business ideas."

    return f"Unknown action: {action}. Use: idea, compete, score, update, list, review, link, stats, boot"
