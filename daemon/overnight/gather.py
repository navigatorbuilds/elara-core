# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight data gathering — collects ALL knowledge into a single context dict.

Reuses existing dream_core gatherers + adds reasoning, outcomes, synthesis,
business, handoff, and memory narrative.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

from core.paths import get_paths

logger = logging.getLogger("elara.overnight")


def gather_all(days: int = 30) -> Dict[str, Any]:
    """
    Gather everything Elara knows into a single dict.

    Wider window than dreams (30 days vs 7) because overnight thinking
    should see the bigger picture.
    """
    logger.info("Gathering knowledge (last %d days)...", days)
    context = {}

    # --- Episodes (via dream_core) ---
    try:
        from daemon.dream_core import _gather_episodes
        context["episodes"] = _gather_episodes(days=days)
        logger.info("  Episodes: %d", len(context["episodes"]))
    except Exception as e:
        logger.warning("  Episodes failed: %s", e)
        context["episodes"] = []

    # --- Goals ---
    try:
        from daemon.dream_core import _gather_goals
        context["goals"] = _gather_goals()
        logger.info("  Goals: %d active, %d stale",
                     len(context["goals"].get("active", [])),
                     len(context["goals"].get("stale", [])))
    except Exception as e:
        logger.warning("  Goals failed: %s", e)
        context["goals"] = {}

    # --- Corrections ---
    try:
        from daemon.dream_core import _gather_corrections
        context["corrections"] = _gather_corrections()
        logger.info("  Corrections: %d", len(context["corrections"]))
    except Exception as e:
        logger.warning("  Corrections failed: %s", e)
        context["corrections"] = []

    # --- Mood journal ---
    try:
        from daemon.dream_core import _gather_mood_journal
        context["mood_journal"] = _gather_mood_journal(days=days)
        logger.info("  Mood entries: %d", len(context["mood_journal"]))
    except Exception as e:
        logger.warning("  Mood journal failed: %s", e)
        context["mood_journal"] = []

    # --- Reasoning trails ---
    try:
        p = get_paths()
        trails = []
        if p.reasoning_dir.exists():
            for f in sorted(p.reasoning_dir.glob("*.json"))[-20:]:
                try:
                    trails.append(json.loads(f.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass
        context["reasoning_trails"] = trails
        logger.info("  Reasoning trails: %d", len(trails))
    except Exception as e:
        logger.warning("  Reasoning trails failed: %s", e)
        context["reasoning_trails"] = []

    # --- Outcomes ---
    try:
        p = get_paths()
        outcomes = []
        if p.outcomes_dir.exists():
            for f in sorted(p.outcomes_dir.glob("*.json"))[-20:]:
                try:
                    outcomes.append(json.loads(f.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass
        context["outcomes"] = outcomes
        logger.info("  Outcomes: %d", len(outcomes))
    except Exception as e:
        logger.warning("  Outcomes failed: %s", e)
        context["outcomes"] = []

    # --- Synthesis (recurring ideas) ---
    try:
        p = get_paths()
        syntheses = []
        if p.synthesis_dir.exists():
            for f in sorted(p.synthesis_dir.glob("*.json"))[-20:]:
                try:
                    syntheses.append(json.loads(f.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass
        context["synthesis"] = syntheses
        logger.info("  Synthesis ideas: %d", len(syntheses))
    except Exception as e:
        logger.warning("  Synthesis failed: %s", e)
        context["synthesis"] = []

    # --- Business ideas ---
    try:
        p = get_paths()
        ideas = []
        if p.business_dir.exists():
            for f in sorted(p.business_dir.glob("*.json")):
                try:
                    ideas.append(json.loads(f.read_text()))
                except (json.JSONDecodeError, OSError):
                    pass
        context["business_ideas"] = ideas
        logger.info("  Business ideas: %d", len(ideas))
    except Exception as e:
        logger.warning("  Business ideas failed: %s", e)
        context["business_ideas"] = []

    # --- Handoff (current session state) ---
    try:
        p = get_paths()
        if p.handoff_file.exists():
            context["handoff"] = json.loads(p.handoff_file.read_text())
            logger.info("  Handoff: loaded")
        else:
            context["handoff"] = {}
    except (json.JSONDecodeError, OSError):
        context["handoff"] = {}

    # --- Memory narrative (the memory.md-like file) ---
    try:
        memory_path = Path.home() / ".claude" / "elara-memory.md"
        if memory_path.exists():
            context["memory_narrative"] = memory_path.read_text()[:4000]
            logger.info("  Memory narrative: loaded (%d chars)",
                       len(context["memory_narrative"]))
        else:
            context["memory_narrative"] = ""
    except OSError:
        context["memory_narrative"] = ""

    # --- Latest dream reports ---
    try:
        from daemon.dream_core import read_latest_dream
        for dtype in ("weekly", "monthly"):
            report = read_latest_dream(dtype)
            if report:
                context[f"dream_{dtype}"] = report.get("summary", "")
                logger.info("  Dream %s: loaded", dtype)
    except Exception as e:
        logger.warning("  Dream reports failed: %s", e)

    logger.info("Knowledge gathering complete.")
    return context


def format_context_for_prompt(context: Dict[str, Any], max_chars: int = 6000) -> str:
    """
    Format gathered context into a text block for LLM prompts.

    Prioritizes the most useful data and truncates to stay within limits.
    """
    sections = []

    # Memory narrative (high value, already text)
    if context.get("memory_narrative"):
        sections.append(("MEMORY OVERVIEW", context["memory_narrative"][:1200]))

    # Handoff (current state)
    if context.get("handoff"):
        h = context["handoff"]
        lines = []
        for key in ("next_plans", "reminders", "unfinished", "promises"):
            items = h.get(key, [])
            if items:
                lines.append(f"  {key}:")
                for item in items[:5]:
                    text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    carried = item.get("carried", 0) if isinstance(item, dict) else 0
                    lines.append(f"    - {text}" + (f" (carried {carried}x)" if carried else ""))
        if h.get("mood_and_mode"):
            lines.append(f"  mood: {h['mood_and_mode']}")
        if lines:
            sections.append(("CURRENT HANDOFF", "\n".join(lines)))

    # Goals
    goals = context.get("goals", {})
    if goals:
        lines = []
        for g in goals.get("active", [])[:8]:
            lines.append(f"  - [{g.get('priority','?')}] {g.get('title','?')} (project: {g.get('project','none')})")
        for g in goals.get("stale", [])[:5]:
            lines.append(f"  - [STALE] {g.get('title','?')}")
        if lines:
            sections.append(("GOALS", "\n".join(lines)))

    # Corrections
    corrections = context.get("corrections", [])
    if corrections:
        lines = []
        for c in corrections[:5]:
            lines.append(f"  - Mistake: {c.get('mistake','?')}")
            lines.append(f"    Fix: {c.get('correction','?')}")
        sections.append(("CORRECTIONS", "\n".join(lines)))

    # Episodes summary
    episodes = context.get("episodes", [])
    if episodes:
        lines = []
        for ep in episodes[-10:]:
            summary = ep.get("summary") or "no summary"
            projects = ", ".join(ep.get("projects", []))
            lines.append(f"  - {ep.get('started','?')[:10]}: {summary[:100]} [{projects}]")
        sections.append(("RECENT EPISODES", "\n".join(lines)))

    # Business ideas
    ideas = context.get("business_ideas", [])
    if ideas:
        lines = []
        for idea in ideas[:5]:
            score = idea.get("score", {})
            total = score.get("total", "?") if score else "unscored"
            lines.append(f"  - {idea.get('name','?')} ({idea.get('status','?')}, score: {total})")
        sections.append(("BUSINESS IDEAS", "\n".join(lines)))

    # Reasoning trails
    trails = context.get("reasoning_trails", [])
    if trails:
        lines = []
        for t in trails[-5:]:
            status = "SOLVED" if t.get("resolved") else "OPEN"
            lines.append(f"  - [{status}] {t.get('context','?')[:80]}")
        sections.append(("REASONING TRAILS", "\n".join(lines)))

    # Synthesis
    syntheses = context.get("synthesis", [])
    if syntheses:
        lines = []
        for s in syntheses[:5]:
            lines.append(f"  - {s.get('concept','?')} ({s.get('status','?')}, {len(s.get('seeds',[]))} seeds)")
        sections.append(("RECURRING IDEAS", "\n".join(lines)))

    # Dream summaries
    for dtype in ("weekly", "monthly"):
        key = f"dream_{dtype}"
        if context.get(key):
            sections.append((f"LATEST {dtype.upper()} DREAM", str(context[key])[:400]))

    # Assemble with budget
    output = []
    total = 0
    for title, body in sections:
        block = f"=== {title} ===\n{body}\n"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                output.append(block[:remaining] + "\n[...truncated]")
            break
        output.append(block)
        total += len(block)

    return "\n".join(output)
