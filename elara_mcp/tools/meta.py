# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Meta-tool: elara_do — dispatches to any registered tool by short name.

Only loaded in lean profile. Registered directly via @mcp.tool() so it
always gets a full MCP schema.

Cortical integration: elara_do runs dispatched tools in the thread pool
executor so they don't block the MCP event loop.
"""

import asyncio
import inspect
import json
from concurrent.futures import ThreadPoolExecutor

from elara_mcp._app import mcp, _TOOL_REGISTRY, _CORE_TOOLS, _executor


@mcp.tool()
async def elara_do(tool: str, params: str = "{}") -> str:
    """
    Run any Elara tool by short name. Use this to access all tools not
    loaded as individual schemas in lean profile.

    Args:
        tool: Tool name without "elara_" prefix. Examples: "goal", "dream", "gmail".
        params: JSON string of parameters. Example: '{"action": "list"}'

    Available tools and key params:

    MOOD & PRESENCE:
      mood_adjust(valence, energy, openness, reason)
      imprint(feeling, strength)
      mode(mode)  — girlfriend/dev/cold/drift/soft/playful/therapist

    MEMORY:
      conversations(action)  — stats | ingest

    EPISODES:
      episode_start(session_type, project)
      episode_note(event, note_type, importance, project, why, confidence)
      episode_end(summary, was_meaningful)
      episode_query(query, project, n, session_type, current, stats)

    GOALS & CORRECTIONS:
      goal(action, title, goal_id, status, project, notes, priority)
      goal_boot()
      correction(action, task, mistake, correction, context, correction_type, fails_when, fine_when)
      correction_boot()

    AWARENESS:
      reflect()
      insight(insight_type)  — pulse | blind_spots | user_state | both
      intention(what)
      observe(when)  — boot | now
      temperament(do_reset)

    DREAMS:
      dream(dream_type)  — weekly | monthly | emotional
      dream_info(action, dream_type)

    COGNITIVE:
      reasoning(action, query, trail_id, context, hypothesis, ...)
      outcome(action, outcome_id, decision, context, predicted, actual, assessment, ...)
      synthesis(action, synthesis_id, concept, quote, source, status)

    COGNITION 3D:
      model(action, model_id, statement, domain, evidence_text, direction, ...)
      prediction(action, prediction_id, statement, confidence, deadline, ...)
      principle(action, principle_id, statement, domain, query, ...)

    WORKFLOWS:
      workflow(action, workflow_id, query, name, domain, trigger, steps, tags, n)

    BUSINESS:
      business(action, idea_id, name, description, ...)

    LLM:
      llm(action, prompt, text, categories)

    GMAIL:
      gmail(action, message_id, thread_id, query, to, subject, body, ...)

    KNOWLEDGE GRAPH:
      kg_index(path, doc_id, version)
      kg_query(query, doc, type, semantic_id)
      kg_validate(docs)
      kg_diff(doc_id, v1, v2)

    MAINTENANCE:
      rebuild_indexes(collection)
      briefing(action, query, n, feed_name, url, category, keywords)
      snapshot()
      memory_consolidation(action, resolve_ids)

    NETWORK:
      network(action, host, port, record_id, limit)

    Returns:
        Tool output or error message
    """
    # Normalize: strip prefix if provided
    name = tool.strip()
    if name.startswith("elara_"):
        name = name[len("elara_"):]

    full_name = f"elara_{name}"

    # Look up in registry (raw sync functions)
    fn = _TOOL_REGISTRY.get(full_name)
    if fn is None:
        available = sorted(
            k.replace("elara_", "")
            for k in _TOOL_REGISTRY
            if k not in _CORE_TOOLS
        )
        return (
            f"Unknown tool: '{name}'\n\n"
            f"Available tools ({len(available)}):\n"
            + "\n".join(f"  {t}" for t in available)
        )

    # Parse params JSON
    try:
        kwargs = json.loads(params)
    except json.JSONDecodeError as e:
        return f"Invalid JSON in params: {e}\n\nGot: {params[:200]}"

    if not isinstance(kwargs, dict):
        return f"params must be a JSON object, got {type(kwargs).__name__}"

    # Validate params against function signature
    sig = inspect.signature(fn)
    try:
        sig.bind(**kwargs)
    except TypeError as e:
        param_info = []
        for pname, param in sig.parameters.items():
            if param.default is inspect.Parameter.empty:
                param_info.append(f"  {pname} (required)")
            else:
                param_info.append(f"  {pname} = {param.default!r}")
        return (
            f"Parameter error for '{name}': {e}\n\n"
            f"Expected signature:\n" + "\n".join(param_info)
        )

    # Dispatch via executor — non-blocking
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: fn(**kwargs))
    except Exception as e:
        return f"Error running '{name}': {type(e).__name__}: {e}"
