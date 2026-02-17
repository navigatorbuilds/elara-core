# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Workflow Patterns MCP tool: learned action sequences.

1 tool for proactive workflow pattern management.
"""

import json
from typing import Optional
from elara_mcp._app import tool


@tool()
def elara_workflow(
    action: str = "list",
    workflow_id: Optional[str] = None,
    query: Optional[str] = None,
    name: Optional[str] = None,
    domain: Optional[str] = None,
    trigger: Optional[str] = None,
    steps: Optional[str] = None,
    tags: Optional[str] = None,
    n: int = 10,
) -> str:
    """
    Workflow patterns — learned action sequences from episode history.

    Workflows are proactive: when you start a task matching a known
    trigger, remaining steps are surfaced automatically.

    Args:
        action: What to do:
            "list"     — List workflows (optional domain, status via domain)
            "search"   — Semantic search (needs query)
            "get"      — Get a single workflow (needs workflow_id)
            "create"   — Create manually (needs name, trigger, steps)
            "complete" — Mark workflow as completed (needs workflow_id)
            "skip"     — Mark workflow as skipped (needs workflow_id)
            "stats"    — Aggregate statistics
        workflow_id: Workflow ID (for get, complete, skip)
        query: Search query (for search)
        name: Workflow name (for create)
        domain: Domain: development, deployment, documentation, maintenance
        trigger: What starts this workflow (for create)
        steps: JSON array of steps, each: {"action": "...", "artifact": "..."}
        tags: Comma-separated tags (for create)
        n: Number of results (for list/search)

    Returns:
        Workflow info, list, or stats
    """
    from daemon.workflows import (
        create_workflow, get_workflow, list_workflows,
        search_workflows, record_completion, record_skip,
        get_workflow_stats,
    )
    from daemon.schemas import ElaraNotFoundError

    if action == "list":
        workflows = list_workflows(domain=domain)
        if not workflows:
            return "No workflows yet."
        wfs = workflows[:n]
        lines = [f"{len(wfs)} workflow(s):"]
        for w in wfs:
            step_names = [s.get("action", "?")[:30] for s in w.get("steps", [])]
            lines.append(
                f"  [{w['workflow_id'][:8]}] {w['name'][:50]}\n"
                f"    {w['domain']} | conf={w['confidence']} | {w['status']} | "
                f"matched={w.get('times_matched',0)}x completed={w.get('times_completed',0)}x\n"
                f"    Trigger: {w.get('trigger','?')[:60]}\n"
                f"    Steps: {' → '.join(step_names)}"
            )
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required for search."
        results = search_workflows(query, n=n)
        if not results:
            return "No matching workflows."
        lines = [f"Found {len(results)} workflow(s):"]
        for w in results:
            sim = w.get("_similarity", "")
            sim_str = f" (sim={sim})" if sim else ""
            step_names = [s.get("action", "?")[:30] for s in w.get("steps", [])]
            lines.append(
                f"  [{w['workflow_id'][:8]}] {w['name'][:50]}{sim_str}\n"
                f"    Trigger: {w.get('trigger','?')[:60]}\n"
                f"    Steps: {' → '.join(step_names)}"
            )
        return "\n".join(lines)

    if action == "get":
        if not workflow_id:
            return "Error: workflow_id is required."
        w = get_workflow(workflow_id)
        if not w:
            return f"Workflow {workflow_id} not found."
        lines = [
            f"Workflow: {w['workflow_id']}",
            f"  Name: {w['name']}",
            f"  Domain: {w['domain']} | Status: {w['status']}",
            f"  Trigger: {w['trigger']}",
            f"  Confidence: {w['confidence']}",
            f"  Matched: {w.get('times_matched', 0)} | "
            f"Completed: {w.get('times_completed', 0)} | "
            f"Skipped: {w.get('times_skipped', 0)}",
            f"  Created: {w.get('created', '?')[:19]}",
        ]
        if w.get("last_matched"):
            lines.append(f"  Last matched: {w['last_matched'][:19]}")
        if w.get("source_episodes"):
            lines.append(f"  Source episodes: {', '.join(w['source_episodes'][:5])}")
        if w.get("tags"):
            lines.append(f"  Tags: {', '.join(w['tags'])}")
        if w.get("steps"):
            lines.append(f"  Steps ({len(w['steps'])}):")
            for i, s in enumerate(w["steps"], 1):
                artifact = f" [{s['artifact']}]" if s.get("artifact") else ""
                lines.append(f"    {i}. {s['action']}{artifact}")
        return "\n".join(lines)

    if action == "create":
        if not name or not trigger:
            return "Error: name and trigger are required for create."
        # Parse steps JSON
        parsed_steps = []
        if steps:
            try:
                parsed_steps = json.loads(steps)
                if not isinstance(parsed_steps, list):
                    return "Error: steps must be a JSON array."
            except json.JSONDecodeError as e:
                return f"Error: invalid JSON in steps: {e}"

        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        w = create_workflow(
            name=name,
            domain=domain or "development",
            trigger=trigger,
            steps=parsed_steps,
            tags=tag_list,
        )
        return (
            f"Workflow created: {w['workflow_id']}\n"
            f"  Name: {w['name']}\n"
            f"  Trigger: {w['trigger']}\n"
            f"  Steps: {len(w.get('steps', []))}"
        )

    if action == "complete":
        if not workflow_id:
            return "Error: workflow_id is required."
        try:
            record_completion(workflow_id)
            w = get_workflow(workflow_id)
            return (
                f"Workflow completed: {workflow_id[:8]}\n"
                f"  {w['name'] if w else '?'}\n"
                f"  Completed {w.get('times_completed', 0)}x | "
                f"Confidence: {w.get('confidence', 0)}"
            )
        except ElaraNotFoundError as e:
            return str(e)

    if action == "skip":
        if not workflow_id:
            return "Error: workflow_id is required."
        try:
            record_skip(workflow_id)
            w = get_workflow(workflow_id)
            return (
                f"Workflow skipped: {workflow_id[:8]}\n"
                f"  {w['name'] if w else '?'}\n"
                f"  Skipped {w.get('times_skipped', 0)}x | "
                f"Confidence: {w.get('confidence', 0)} | Status: {w.get('status', '?')}"
            )
        except ElaraNotFoundError as e:
            return str(e)

    if action == "stats":
        stats = get_workflow_stats()
        if stats["total"] == 0:
            return "No workflows yet."
        lines = [
            f"Workflows: {stats['total']} total",
            f"  By status: {stats['by_status']}",
            f"  By domain: {stats['by_domain']}",
            f"  Total matches: {stats['total_matches']}",
            f"  Total completions: {stats['total_completions']}",
            f"  Total skips: {stats['total_skips']}",
        ]
        if stats["avg_confidence"] is not None:
            lines.append(f"  Avg confidence (active): {stats['avg_confidence']}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: list, search, get, create, complete, skip, stats"
