# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Cognitive layer tools: reasoning trails, outcome tracking, idea synthesis.

3 tools, dispatch via action parameter (consistent with other modules).
"""

from typing import Optional
from elara_mcp._app import tool
from daemon.schemas import ElaraNotFoundError, ElaraValidationError
from daemon.reasoning import (
    start_trail, add_hypothesis, update_hypothesis,
    abandon_approach, solve_trail, search_trails,
    get_trail, get_active_trail, list_trails,
    get_recurring_problem_tags, get_abandonment_rate,
)
from daemon.outcomes import (
    record_outcome, check_outcome, get_outcome,
    list_outcomes, search_outcomes_by_tags,
    get_outcome_stats, get_unchecked_outcomes,
    record_pitch, get_pitch_stats, get_pitch_lessons,
)
from daemon.synthesis import (
    create_synthesis, add_seed, update_status,
    get_synthesis, list_syntheses, get_ready_ideas,
    get_synthesis_stats,
)


@tool()
def elara_reasoning(
    action: str = "search",
    query: Optional[str] = None,
    trail_id: Optional[str] = None,
    context: Optional[str] = None,
    hypothesis: Optional[str] = None,
    hypothesis_index: Optional[int] = None,
    evidence: Optional[str] = None,
    confidence: Optional[float] = None,
    outcome: Optional[str] = None,
    solution: Optional[str] = None,
    breakthrough: Optional[str] = None,
    approach: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """
    Reasoning trails — track problem-solving chains for future reference.

    Args:
        action: What to do:
            "start"      — Begin a new trail (needs context)
            "hypothesis" — Add a hypothesis to active/specified trail
            "evidence"   — Add evidence to a hypothesis
            "abandon"    — Record an abandoned approach
            "solve"      — Mark trail as solved
            "search"     — Search past trails by problem similarity
            "status"     — Show active trail or stats
            "list"       — List recent trails
        query: Search query (for search action)
        trail_id: Trail ID (auto-uses active trail if omitted)
        context: Problem description (for start)
        hypothesis: The hypothesis text (for hypothesis action)
        hypothesis_index: Which hypothesis to update (0-indexed)
        evidence: Evidence text (comma-separated for multiple)
        confidence: Confidence level 0.0-1.0
        outcome: Hypothesis outcome: "true", "false", "partial"
        solution: What actually worked (for solve)
        breakthrough: What triggered the breakthrough (for solve)
        approach: Abandoned approach description (for abandon)
        tags: Comma-separated tags

    Returns:
        Trail info, search results, or stats
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    evidence_list = [e.strip() for e in evidence.split(",")] if evidence else None

    if action == "start":
        if not context:
            return "Error: context is required to start a trail."
        trail = start_trail(context=context, tags=tag_list)
        lines = [f"Trail started: {trail['trail_id']}", f"Context: {context}"]
        if tag_list:
            lines.append(f"Tags: {', '.join(tag_list)}")
        return "\n".join(lines)

    if action == "hypothesis":
        if not hypothesis:
            return "Error: hypothesis text is required."
        tid = trail_id or _active_trail_id()
        if not tid:
            return "Error: no active trail. Start one first or provide trail_id."
        try:
            result = add_hypothesis(tid, hypothesis, evidence_list, confidence or 0.5)
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)
        idx = len(result["hypotheses"]) - 1
        return f"Hypothesis #{idx} added to trail {tid}: {hypothesis} (confidence: {confidence or 0.5})"

    if action == "evidence":
        if hypothesis_index is None:
            return "Error: hypothesis_index is required."
        tid = trail_id or _active_trail_id()
        if not tid:
            return "Error: no active trail."
        try:
            result = update_hypothesis(tid, hypothesis_index, outcome=outcome, evidence=evidence_list, confidence=confidence)
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)
        h = result["hypotheses"][hypothesis_index]
        parts = [f"Hypothesis #{hypothesis_index} updated"]
        if outcome:
            parts.append(f"outcome={outcome}")
        if evidence_list:
            parts.append(f"+{len(evidence_list)} evidence")
        if confidence is not None:
            parts.append(f"confidence={confidence}")
        return " | ".join(parts)

    if action == "abandon":
        if not approach:
            return "Error: approach description is required."
        tid = trail_id or _active_trail_id()
        if not tid:
            return "Error: no active trail."
        try:
            result = abandon_approach(tid, approach)
        except ElaraNotFoundError as e:
            return str(e)
        n = len(result["abandoned_approaches"])
        return f"Approach abandoned ({n} total): {approach}"

    if action == "solve":
        if not solution:
            return "Error: solution is required."
        tid = trail_id or _active_trail_id()
        if not tid:
            return "Error: no active trail."
        try:
            result = solve_trail(tid, solution, breakthrough, tag_list)
        except ElaraNotFoundError as e:
            return str(e)
        lines = [f"Trail {tid} solved!", f"Solution: {solution}"]
        if breakthrough:
            lines.append(f"Breakthrough: {breakthrough}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required for search."
        results = search_trails(query, n=5)
        if not results:
            return "No matching trails found."
        lines = [f"Found {len(results)} trail(s):"]
        for t in results:
            sim = t.get("_similarity", "?")
            resolved = "solved" if t.get("resolved") else "open"
            lines.append(f"  [{sim}] {t['trail_id']} ({resolved}): {t['context'][:80]}")
            if t.get("final_solution"):
                lines.append(f"         Solution: {t['final_solution'][:80]}")
        return "\n".join(lines)

    if action == "status":
        active = get_active_trail()
        stats = get_abandonment_rate()
        recurring = get_recurring_problem_tags(min_count=2)

        lines = []
        if active:
            lines.append(f"Active trail: {active['trail_id']}")
            lines.append(f"  Context: {active['context'][:100]}")
            lines.append(f"  Hypotheses: {len(active.get('hypotheses', []))}")
            lines.append(f"  Abandoned: {len(active.get('abandoned_approaches', []))}")
        else:
            lines.append("No active trail.")

        lines.append(f"\nTotal trails: {stats['total_trails']}")
        lines.append(f"Unresolved: {stats['unresolved']}")
        lines.append(f"Avg abandoned approaches: {stats['avg_per_trail']}")

        if recurring:
            lines.append("\nRecurring problem areas:")
            for r in recurring[:5]:
                lines.append(f"  [{r['tag']}] — {r['count']} trails")

        return "\n".join(lines)

    if action == "list":
        trails = list_trails(n=10)
        if not trails:
            return "No reasoning trails yet."
        lines = [f"{len(trails)} trail(s):"]
        for t in trails:
            status = "solved" if t.get("resolved") else "open"
            tags_str = ", ".join(t.get("tags", []))
            lines.append(f"  {t['trail_id']} ({status}) [{tags_str}]: {t['context'][:60]}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: start, hypothesis, evidence, abandon, solve, search, status, list"


@tool()
def elara_outcome(
    action: str = "list",
    outcome_id: Optional[str] = None,
    decision: Optional[str] = None,
    context: Optional[str] = None,
    predicted: Optional[str] = None,
    actual: Optional[str] = None,
    assessment: Optional[str] = None,
    lesson: Optional[str] = None,
    reasoning_trail: Optional[str] = None,
    tags: Optional[str] = None,
    idea_id: Optional[str] = None,
    channel: Optional[str] = None,
    audience: Optional[str] = None,
    framing: Optional[str] = None,
) -> str:
    """
    Outcome tracking — link decisions to results, close the learning loop.

    Args:
        action: What to do:
            "record"  — Record a decision and prediction
            "check"   — Check a decision against reality
            "list"    — List recent outcomes
            "stats"   — Win rate and patterns
            "search"  — Search by tags before making similar decisions
            "pitch"   — Record a pitch attempt (needs idea_id, channel, audience, framing, predicted)
            "pitch_stats" — Win rate by channel/framing for an idea (needs idea_id)
            "pitch_lessons" — Lessons from past pitches (needs idea_id)
        outcome_id: Outcome ID (for check)
        decision: What we decided (for record)
        context: Why we decided it (for record)
        predicted: What we expected (for record/pitch)
        actual: What actually happened (for check)
        assessment: "win", "partial_win", "loss", "too_early" (for check)
        lesson: One-line takeaway (for check)
        reasoning_trail: Link to a reasoning trail ID (for record)
        tags: Comma-separated tags
        idea_id: Business idea ID (for pitch actions)
        channel: Where we pitched: reddit, twitter, etc. (for pitch)
        audience: Who we pitched to (for pitch)
        framing: How we framed it: problem-story, feature-list, etc. (for pitch)

    Returns:
        Outcome info, list, or stats
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    if action == "record":
        if not all([decision, context, predicted]):
            return "Error: decision, context, and predicted are all required."
        result = record_outcome(decision, context, predicted, tag_list, reasoning_trail)
        lines = [
            f"Outcome recorded: {result['outcome_id']}",
            f"Decision: {decision}",
            f"Predicted: {predicted}",
            "Status: too_early (check back later with action=check)",
        ]
        return "\n".join(lines)

    if action == "check":
        if not outcome_id:
            return "Error: outcome_id is required for check."
        if not all([actual, assessment]):
            return "Error: actual and assessment are required for check."
        try:
            result = check_outcome(outcome_id, actual, assessment, lesson)
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)
        lines = [
            f"Outcome {outcome_id} checked: {assessment}",
            f"Decision: {result['decision']}",
            f"Predicted: {result['predicted']}",
            f"Actual: {actual}",
        ]
        if lesson:
            lines.append(f"Lesson: {lesson}")
        return "\n".join(lines)

    if action == "list":
        unchecked = list_outcomes(unchecked_only=True, n=5)
        recent = list_outcomes(n=10)

        lines = []
        if unchecked:
            lines.append(f"Unchecked ({len(unchecked)}):")
            for o in unchecked:
                lines.append(f"  {o['outcome_id']}: {o['decision'][:60]} (predicted: {o['predicted'][:40]})")
            lines.append("")

        if recent:
            lines.append(f"Recent ({len(recent)}):")
            for o in recent:
                icon = {"win": "+", "partial_win": "~", "loss": "-", "too_early": "?"}
                a = o.get("assessment", "?")
                lines.append(f"  [{icon.get(a, '?')}] {o['outcome_id']}: {o['decision'][:60]}")
        else:
            lines.append("No outcomes recorded yet.")

        return "\n".join(lines)

    if action == "stats":
        stats = get_outcome_stats()
        lines = [
            f"Total outcomes: {stats['total']}",
            f"Checked: {stats['checked']} | Unchecked: {stats['unchecked']}",
            f"Wins: {stats['wins']} | Partial: {stats['partial_wins']} | Losses: {stats['losses']}",
        ]
        if stats["win_rate"] is not None:
            lines.append(f"Win rate: {stats['win_rate']:.0%}")

        from daemon.outcomes import get_loss_patterns
        patterns = get_loss_patterns(min_losses=2)
        if patterns:
            lines.append("\nLoss patterns:")
            for p in patterns[:5]:
                lines.append(f"  [{p['tag']}] — {p['loss_count']} losses")
                for lesson in p.get("lessons", [])[:2]:
                    lines.append(f"    lesson: {lesson}")

        old = get_unchecked_outcomes(days_old=7)
        if old:
            lines.append(f"\nForgotten decisions ({len(old)} unchecked for 7+ days):")
            for o in old[:3]:
                lines.append(f"  {o['outcome_id']}: {o['decision'][:50]} ({o.get('_age_days', '?')}d ago)")

        return "\n".join(lines)

    if action == "search":
        if not tag_list:
            return "Error: tags are required for search."
        results = search_outcomes_by_tags(tag_list, n=5)
        if not results:
            return f"No outcomes found with tags: {', '.join(tag_list)}"
        lines = [f"Found {len(results)} outcome(s) with matching tags:"]
        for o in results:
            a = o.get("assessment", "?")
            lines.append(f"  [{a}] {o['decision'][:60]}")
            if o.get("lesson"):
                lines.append(f"    lesson: {o['lesson']}")
        return "\n".join(lines)

    if action == "pitch":
        if not all([idea_id, channel, audience, framing, predicted]):
            return "Error: idea_id, channel, audience, framing, and predicted are all required."
        result = record_pitch(idea_id, channel, audience, framing, predicted, tag_list)
        return (
            f"Pitch recorded: {result['outcome_id']}\n"
            f"Idea: {idea_id} | Channel: {channel} | Audience: {audience}\n"
            f"Framing: {framing}\n"
            f"Predicted: {predicted}"
        )

    if action == "pitch_stats":
        if not idea_id:
            return "Error: idea_id is required."
        stats = get_pitch_stats(idea_id)
        if stats["total_pitches"] == 0:
            return f"No pitches recorded for {idea_id}."
        lines = [f"Pitch stats for {idea_id}: {stats['total_pitches']} total"]
        if stats["by_channel"]:
            lines.append("By channel:")
            for ch, s in stats["by_channel"].items():
                wr = f" (win rate: {s['win_rate']:.0%})" if s["win_rate"] is not None else ""
                lines.append(f"  {ch}: {s['total']} pitches, {s['wins']}W/{s['losses']}L{wr}")
        if stats["by_framing"]:
            lines.append("By framing:")
            for fr, s in stats["by_framing"].items():
                wr = f" (win rate: {s['win_rate']:.0%})" if s["win_rate"] is not None else ""
                lines.append(f"  {fr}: {s['total']} pitches, {s['wins']}W/{s['losses']}L{wr}")
        return "\n".join(lines)

    if action == "pitch_lessons":
        if not idea_id:
            return "Error: idea_id is required."
        lessons = get_pitch_lessons(idea_id)
        if not lessons:
            return f"No pitch lessons for {idea_id} yet."
        lines = [f"Pitch lessons for {idea_id}:"]
        for l in lessons:
            lines.append(f"  [{l['assessment']}] {l['channel']}/{l['framing']}: {l['lesson']}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: record, check, list, stats, search, pitch, pitch_stats, pitch_lessons"


@tool()
def elara_synthesis(
    action: str = "list",
    synthesis_id: Optional[str] = None,
    concept: Optional[str] = None,
    quote: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """
    Idea synthesis — detect and track recurring half-formed ideas.

    Args:
        action: What to do:
            "create"   — Manually create a synthesis from a recurring idea
            "add_seed" — Add evidence to an existing synthesis
            "activate" — Mark an idea as being worked on
            "abandon"  — Mark an idea as dropped
            "list"     — List all syntheses
            "ready"    — Show ideas ready to act on (3+ seeds)
            "stats"    — Summary statistics
        synthesis_id: Synthesis ID (for add_seed, activate, abandon)
        concept: Short name for the idea (for create)
        quote: The actual words that hinted at this idea
        source: Where the seed came from: "conversation", "memory", "episode"
        status: Filter for list

    Returns:
        Synthesis info, list, or stats
    """
    if action == "create":
        if not concept or not quote:
            return "Error: concept and quote are required."
        synth = create_synthesis(concept, quote, source or "conversation")
        return f"Synthesis created: {synth['synthesis_id']}\nConcept: {concept}\nSeed: {quote[:100]}\nConfidence: {synth['confidence']}"

    if action == "add_seed":
        if not synthesis_id or not quote:
            return "Error: synthesis_id and quote are required."
        try:
            result = add_seed(synthesis_id, quote, source or "conversation")
        except ElaraNotFoundError as e:
            return str(e)
        return f"Seed added to {synthesis_id}. Seeds: {result['times_surfaced']}, Confidence: {result['confidence']}"

    if action in ("activate", "abandon", "implement"):
        if not synthesis_id:
            return "Error: synthesis_id is required."
        new_status = {"activate": "activated", "abandon": "abandoned", "implement": "implemented"}.get(action, action)
        try:
            result = update_status(synthesis_id, new_status)
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)
        return f"Synthesis {synthesis_id} → {new_status}"

    if action == "list":
        syntheses = list_syntheses(status=status, n=15)
        if not syntheses:
            return "No syntheses yet."
        lines = [f"{len(syntheses)} synthesis(es):"]
        for s in syntheses:
            seeds = len(s.get("seeds", []))
            lines.append(f"  [{s['status']}] {s['synthesis_id']}: {s['concept']} ({seeds} seeds, conf={s.get('confidence', 0):.2f})")
        return "\n".join(lines)

    if action == "ready":
        ready = get_ready_ideas(min_seeds=3)
        if not ready:
            return "No ideas ready yet (need 3+ seeds)."
        lines = ["Ideas ready to act on:"]
        for r in ready:
            lines.append(f"  {r['synthesis_id']}: {r['concept']}")
            lines.append(f"    Surfaced {r['times_surfaced']}x, confidence {r['confidence']:.2f}, first seen {r['first_seen'][:10]}")
        return "\n".join(lines)

    if action == "stats":
        stats = get_synthesis_stats()
        lines = [
            f"Total syntheses: {stats['total']}",
            f"Dormant: {stats['dormant']} | Activated: {stats['activated']}",
            f"Implemented: {stats['implemented']} | Abandoned: {stats['abandoned']}",
            f"Total seeds: {stats['total_seeds']} (avg {stats['avg_seeds']}/synthesis)",
        ]
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: create, add_seed, activate, abandon, list, ready, stats"


# ============================================================================
# Helper
# ============================================================================

def _active_trail_id() -> Optional[str]:
    trail = get_active_trail()
    return trail["trail_id"] if trail else None
