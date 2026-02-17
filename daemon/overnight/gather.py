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

    # --- Briefing (RSS feeds) ---
    try:
        from daemon.briefing import search_items
        recent = search_items("", n=20)  # Get 20 most recent items
        context["briefing_items"] = recent if isinstance(recent, list) else []
        logger.info("  Briefing items: %d", len(context.get("briefing_items", [])))
    except Exception as e:
        logger.warning("  Briefing failed: %s", e)
        context["briefing_items"] = []

    # --- 3D Cognition: models, predictions, principles ---
    try:
        from daemon.models import get_active_models
        context["cognitive_models"] = get_active_models()
        logger.info("  Cognitive models: %d active", len(context["cognitive_models"]))
    except Exception as e:
        logger.warning("  Cognitive models failed: %s", e)
        context["cognitive_models"] = []

    try:
        from daemon.predictions import get_pending_predictions, get_prediction_accuracy
        context["predictions_pending"] = get_pending_predictions()
        context["prediction_accuracy"] = get_prediction_accuracy()
        logger.info("  Predictions: %d pending", len(context["predictions_pending"]))
    except Exception as e:
        logger.warning("  Predictions failed: %s", e)
        context["predictions_pending"] = []
        context["prediction_accuracy"] = {}

    try:
        from daemon.principles import get_active_principles
        context["principles"] = get_active_principles()
        logger.info("  Principles: %d active", len(context["principles"]))
    except Exception as e:
        logger.warning("  Principles failed: %s", e)
        context["principles"] = []

    # --- Workflows (learned action sequences) ---
    try:
        from daemon.workflows import list_workflows
        context["workflows"] = list_workflows(status="active")
        logger.info("  Workflows: %d active", len(context["workflows"]))
    except Exception as e:
        logger.warning("  Workflows failed: %s", e)
        context["workflows"] = []

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

    # --- Temporal scales (daily/weekly/monthly aggregation) ---
    try:
        context["temporal"] = gather_temporal_scales(context)
        logger.info("  Temporal scales: daily=%d, weekly=%d, monthly=%d",
                     len(context["temporal"].get("daily", [])),
                     len(context["temporal"].get("weekly", [])),
                     len(context["temporal"].get("monthly", [])))
    except Exception as e:
        logger.warning("  Temporal scales failed: %s", e)
        context["temporal"] = {}

    logger.info("Knowledge gathering complete.")
    return context


def gather_temporal_scales(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate context data across daily, weekly, and monthly scales.

    Uses episodes and mood journal already gathered to build summaries
    at multiple time horizons.
    """
    now = datetime.now()
    result = {"daily": [], "weekly": [], "monthly": []}

    episodes = context.get("episodes", [])
    mood_entries = context.get("mood_journal", [])

    # --- Daily (last 7 days) ---
    for day_offset in range(7):
        day = now - timedelta(days=day_offset)
        day_str = day.strftime("%Y-%m-%d")

        day_eps = [
            e for e in episodes
            if str(e.get("started", ""))[:10] == day_str
        ]
        day_moods = [
            m for m in mood_entries
            if str(m.get("timestamp", ""))[:10] == day_str
        ]

        if not day_eps and not day_moods:
            continue

        projects = set()
        session_types = []
        for e in day_eps:
            projects.update(e.get("projects", []))
            session_types.append(e.get("session_type", "unknown"))

        avg_valence = None
        if day_moods:
            vals = [m.get("valence", 0) for m in day_moods if "valence" in m]
            avg_valence = round(sum(vals) / len(vals), 2) if vals else None

        result["daily"].append({
            "date": day_str,
            "sessions": len(day_eps),
            "projects": list(projects),
            "session_types": session_types,
            "avg_mood": avg_valence,
        })

    # --- Weekly (last 4 weeks) ---
    for week_offset in range(4):
        week_start = now - timedelta(weeks=week_offset, days=now.weekday())
        week_end = week_start + timedelta(days=7)
        week_label = week_start.strftime("%Y-W%W")

        week_eps = [
            e for e in episodes
            if week_start.isoformat()[:10] <= str(e.get("started", ""))[:10] < week_end.isoformat()[:10]
        ]

        if not week_eps:
            continue

        projects = set()
        work_count = 0
        drift_count = 0
        for e in week_eps:
            projects.update(e.get("projects", []))
            st = e.get("session_type", "")
            if st == "work":
                work_count += 1
            elif st == "drift":
                drift_count += 1

        result["weekly"].append({
            "week": week_label,
            "sessions": len(week_eps),
            "projects": list(projects),
            "work_sessions": work_count,
            "drift_sessions": drift_count,
            "work_drift_ratio": round(work_count / max(drift_count, 1), 1),
        })

    # --- Monthly (last 3 months) ---
    for month_offset in range(3):
        # Calculate month
        m = now.month - month_offset
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_str = f"{y}-{m:02d}"

        month_eps = [
            e for e in episodes
            if str(e.get("started", ""))[:7] == month_str
        ]

        if not month_eps:
            continue

        projects = set()
        for e in month_eps:
            projects.update(e.get("projects", []))

        # Model/prediction counts from 3D context
        models = context.get("cognitive_models", [])
        month_models = len([
            m for m in models
            if str(m.get("created", ""))[:7] == month_str
        ])

        result["monthly"].append({
            "month": month_str,
            "sessions": len(month_eps),
            "projects": list(projects),
            "models_created": month_models,
        })

    return result


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

    # Briefing (RSS news)
    briefing = context.get("briefing_items", [])
    if briefing:
        lines = []
        for item in briefing[:10]:
            title = item.get("title", "?") if isinstance(item, dict) else str(item)
            feed = item.get("feed", "") if isinstance(item, dict) else ""
            lines.append(f"  - [{feed}] {title[:100]}")
        sections.append(("EXTERNAL BRIEFING (RSS)", "\n".join(lines)))

    # 3D Cognition: Models
    models = context.get("cognitive_models", [])
    if models:
        lines = []
        for m in models[:10]:
            lines.append(
                f"  - [{m.get('domain','?')}] {m.get('statement','?')[:80]} "
                f"(conf={m.get('confidence',0)}, checks={m.get('check_count',0)})"
            )
        sections.append(("COGNITIVE MODELS", "\n".join(lines)))

    # 3D Cognition: Predictions
    predictions = context.get("predictions_pending", [])
    if predictions:
        lines = []
        for p in predictions[:8]:
            days = p.get("_days_until_deadline", "?")
            lines.append(
                f"  - {p.get('statement','?')[:80]} "
                f"(conf={p.get('confidence',0)}, deadline={p.get('deadline','?')}, {days}d left)"
            )
        accuracy = context.get("prediction_accuracy", {})
        if accuracy.get("checked"):
            lines.append(
                f"  Overall: {accuracy.get('accuracy','?')} accuracy, "
                f"{accuracy.get('checked',0)} checked, {accuracy.get('pending',0)} pending"
            )
        sections.append(("ACTIVE PREDICTIONS", "\n".join(lines)))

    # 3D Cognition: Principles
    principles = context.get("principles", [])
    if principles:
        lines = []
        for p in principles[:8]:
            lines.append(
                f"  - [{p.get('domain','?')}] {p.get('statement','?')[:80]} "
                f"(conf={p.get('confidence',0)}, confirmed={p.get('times_confirmed',0)}x)"
            )
        sections.append(("CRYSTALLIZED PRINCIPLES", "\n".join(lines)))

    # Workflows
    workflows = context.get("workflows", [])
    if workflows:
        lines = []
        for w in workflows[:8]:
            steps = [s.get("action", "?")[:30] for s in w.get("steps", [])]
            lines.append(
                f"  - [{w.get('domain','?')}] {w.get('name','?')[:50]} "
                f"(conf={w.get('confidence',0)}, matched={w.get('times_matched',0)}x)\n"
                f"    Trigger: {w.get('trigger','?')[:60]}\n"
                f"    Steps: {' → '.join(steps)}"
            )
        sections.append(("WORKFLOW PATTERNS", "\n".join(lines)))

    # Temporal scales
    temporal = context.get("temporal", {})
    if temporal:
        lines = []
        daily = temporal.get("daily", [])
        if daily:
            lines.append("  Daily (last 7d):")
            for d in daily[:7]:
                mood = f", mood={d['avg_mood']}" if d.get("avg_mood") is not None else ""
                lines.append(
                    f"    {d['date']}: {d['sessions']} sessions, "
                    f"projects=[{', '.join(d.get('projects', [])[:3])}]{mood}"
                )
        weekly = temporal.get("weekly", [])
        if weekly:
            lines.append("  Weekly:")
            for w in weekly[:4]:
                lines.append(
                    f"    {w['week']}: {w['sessions']} sessions, "
                    f"work/drift={w.get('work_drift_ratio', '?')}, "
                    f"projects=[{', '.join(w.get('projects', [])[:4])}]"
                )
        monthly = temporal.get("monthly", [])
        if monthly:
            lines.append("  Monthly:")
            for m in monthly[:3]:
                lines.append(
                    f"    {m['month']}: {m['sessions']} sessions, "
                    f"{m.get('models_created', 0)} models, "
                    f"projects=[{', '.join(m.get('projects', [])[:5])}]"
                )
        if lines:
            sections.append(("TEMPORAL OVERVIEW", "\n".join(lines)))

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
