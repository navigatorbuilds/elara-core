# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""3D Cognition MCP tools: models, predictions, principles.

3 tools for persistent understanding, foresight, and wisdom.
"""

import json
from typing import Optional
from elara_mcp._app import mcp


@mcp.tool()
def elara_model(
    action: str = "list",
    model_id: Optional[str] = None,
    statement: Optional[str] = None,
    domain: Optional[str] = None,
    evidence_text: Optional[str] = None,
    direction: str = "supports",
    confidence: Optional[float] = None,
    source: str = "manual",
    query: Optional[str] = None,
    tags: Optional[str] = None,
    n: int = 10,
) -> str:
    """
    Cognitive models — persistent understanding that accumulates over time.

    Models are statements about the world, user, or work patterns.
    They strengthen with evidence, weaken with contradictions, and
    the overnight brain checks them automatically.

    Args:
        action: What to do:
            "create"     — Create a new model (needs statement)
            "evidence"   — Add evidence to a model (needs model_id, evidence_text)
            "get"        — Get a single model (needs model_id)
            "search"     — Semantic search (needs query)
            "list"       — List models (optional domain, status filter via domain)
            "stats"      — Aggregate statistics
            "invalidate" — Directly invalidate a model (needs model_id)
        model_id: Model ID (for evidence, get, invalidate)
        statement: Model statement (for create)
        domain: Domain filter or assignment: work_patterns, emotional, project,
                behavioral, technical, general
        evidence_text: Evidence text (for evidence action)
        direction: Evidence direction: supports (+0.05), weakens (-0.08),
                   invalidates (-0.30). Default: supports
        confidence: Initial confidence 0-1 (for create, default 0.5)
        source: Evidence source (for evidence action)
        query: Search query (for search)
        tags: Comma-separated tags (for create)
        n: Number of results (for list/search)

    Returns:
        Model info, list, or stats
    """
    from daemon.models import (
        create_model, add_evidence, get_model, search_models,
        list_models, get_model_stats, invalidate_model, get_active_models,
    )
    from daemon.schemas import ElaraNotFoundError

    if action == "create":
        if not statement:
            return "Error: statement is required for create."
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        model = create_model(
            statement=statement,
            domain=domain or "general",
            evidence_text=evidence_text,
            confidence=confidence or 0.5,
            tags=tag_list,
        )
        return (
            f"Model created: {model['model_id']}\n"
            f"  Statement: {model['statement'][:100]}\n"
            f"  Domain: {model['domain']}, Confidence: {model['confidence']}\n"
            f"  Evidence: {len(model.get('evidence', []))} items"
        )

    if action == "evidence":
        if not model_id or not evidence_text:
            return "Error: model_id and evidence_text are required."
        try:
            model = add_evidence(model_id, evidence_text, source=source, direction=direction)
            return (
                f"Evidence added to {model_id} ({direction})\n"
                f"  Confidence: {model['confidence']} | Status: {model['status']}\n"
                f"  Total evidence: {len(model.get('evidence', []))}"
            )
        except ElaraNotFoundError as e:
            return str(e)

    if action == "get":
        if not model_id:
            return "Error: model_id is required."
        model = get_model(model_id)
        if not model:
            return f"Model {model_id} not found."
        lines = [
            f"Model: {model['model_id']}",
            f"  Statement: {model['statement']}",
            f"  Domain: {model['domain']} | Status: {model['status']}",
            f"  Confidence: {model['confidence']}",
            f"  Checks: {model.get('check_count', 0)} | "
            f"Strengthened: {model.get('strengthen_count', 0)} | "
            f"Weakened: {model.get('weaken_count', 0)}",
            f"  Created: {model.get('created', '?')[:19]}",
            f"  Last checked: {model.get('last_checked', '?')[:19]}",
        ]
        if model.get("tags"):
            lines.append(f"  Tags: {', '.join(model['tags'])}")
        if model.get("evidence"):
            lines.append(f"  Evidence ({len(model['evidence'])} items):")
            for ev in model["evidence"][-5:]:
                lines.append(f"    [{ev.get('direction', '?')}] {ev.get('text', '')[:80]}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required for search."
        results = search_models(query, n=n)
        if not results:
            return "No matching models."
        lines = [f"Found {len(results)} model(s):"]
        for m in results:
            sim = m.get("_similarity", "")
            sim_str = f" (sim={sim})" if sim else ""
            lines.append(
                f"  [{m['model_id'][:8]}] {m['statement'][:60]}{sim_str}\n"
                f"    {m['domain']} | conf={m['confidence']} | {m['status']}"
            )
        return "\n".join(lines)

    if action == "list":
        models = list_models(domain=domain, n=n)
        if not models:
            return "No models found."
        lines = [f"{len(models)} model(s):"]
        for m in models:
            lines.append(
                f"  [{m['model_id'][:8]}] {m['statement'][:60]}\n"
                f"    {m['domain']} | conf={m['confidence']} | {m['status']}"
            )
        return "\n".join(lines)

    if action == "stats":
        stats = get_model_stats()
        if stats["total"] == 0:
            return "No models yet."
        lines = [
            f"Models: {stats['total']} total",
            f"  By status: {stats['by_status']}",
            f"  By domain: {stats['by_domain']}",
        ]
        if stats["avg_confidence"] is not None:
            lines.append(f"  Avg confidence (active): {stats['avg_confidence']}")
        return "\n".join(lines)

    if action == "invalidate":
        if not model_id:
            return "Error: model_id is required."
        try:
            model = invalidate_model(model_id)
            return f"Model {model_id} invalidated. Was: {model['statement'][:80]}"
        except ElaraNotFoundError as e:
            return str(e)

    return f"Unknown action: {action}. Use: create, evidence, get, search, list, stats, invalidate"


@mcp.tool()
def elara_prediction(
    action: str = "list",
    prediction_id: Optional[str] = None,
    statement: Optional[str] = None,
    confidence: Optional[float] = None,
    deadline: Optional[str] = None,
    source_model: Optional[str] = None,
    actual_outcome: Optional[str] = None,
    status: Optional[str] = None,
    lesson: Optional[str] = None,
    query: Optional[str] = None,
    tags: Optional[str] = None,
    days_ahead: int = 14,
    n: int = 10,
) -> str:
    """
    Predictions — explicit forecasts with deadlines and verification.

    The brain makes predictions based on models. When deadlines pass,
    predictions get checked. Accuracy rates calibrate confidence.

    Args:
        action: What to do:
            "predict"   — Make a prediction (needs statement)
            "check"     — Check against reality (needs prediction_id, actual_outcome, status)
            "get"       — Get a single prediction (needs prediction_id)
            "pending"   — Show upcoming predictions (optional days_ahead)
            "expired"   — Show overdue predictions needing verification
            "accuracy"  — Prediction accuracy stats
            "search"    — Semantic search (needs query)
            "list"      — List predictions (optional status filter)
        prediction_id: Prediction ID (for check, get)
        statement: What we predict (for predict)
        confidence: How confident 0-1 (for predict, default 0.5)
        deadline: When to check (ISO date, default +14 days)
        source_model: Model ID this prediction is based on
        actual_outcome: What actually happened (for check)
        status: Prediction status for check: correct, wrong, partially_correct, expired
        lesson: What we learned (for check)
        query: Search query
        tags: Comma-separated tags
        days_ahead: How far ahead to look for pending (default 14)
        n: Number of results

    Returns:
        Prediction info, list, accuracy stats
    """
    from daemon.predictions import (
        make_prediction, check_prediction, get_prediction,
        get_pending_predictions, check_expired_predictions,
        get_prediction_accuracy, search_predictions,
        list_predictions,
    )
    from daemon.schemas import ElaraNotFoundError, ElaraValidationError

    if action == "predict":
        if not statement:
            return "Error: statement is required."
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        pred = make_prediction(
            statement=statement,
            confidence=confidence or 0.5,
            deadline=deadline or "",
            source_model=source_model,
            tags=tag_list,
        )
        return (
            f"Prediction made: {pred['prediction_id']}\n"
            f"  {pred['statement'][:100]}\n"
            f"  Confidence: {pred['confidence']} | Deadline: {pred['deadline']}"
        )

    if action == "check":
        if not prediction_id or not actual_outcome or not status:
            return "Error: prediction_id, actual_outcome, and status are required."
        try:
            pred = check_prediction(prediction_id, actual_outcome, status, lesson=lesson)
            return (
                f"Prediction checked: {status}\n"
                f"  Predicted: {pred['statement'][:80]}\n"
                f"  Actual: {actual_outcome[:80]}\n"
                f"  Lesson: {lesson or '(none)'}"
            )
        except (ElaraNotFoundError, ElaraValidationError) as e:
            return str(e)

    if action == "get":
        if not prediction_id:
            return "Error: prediction_id is required."
        pred = get_prediction(prediction_id)
        if not pred:
            return f"Prediction {prediction_id} not found."
        lines = [
            f"Prediction: {pred['prediction_id']}",
            f"  {pred['statement']}",
            f"  Confidence: {pred['confidence']} | Status: {pred['status']}",
            f"  Deadline: {pred['deadline']}",
            f"  Created: {pred.get('created', '?')[:19]}",
        ]
        if pred.get("source_model"):
            lines.append(f"  Source model: {pred['source_model']}")
        if pred.get("actual_outcome"):
            lines.append(f"  Actual: {pred['actual_outcome']}")
        if pred.get("lesson"):
            lines.append(f"  Lesson: {pred['lesson']}")
        if pred.get("tags"):
            lines.append(f"  Tags: {', '.join(pred['tags'])}")
        return "\n".join(lines)

    if action == "pending":
        pending = get_pending_predictions(days_ahead=days_ahead)
        if not pending:
            return "No pending predictions."
        lines = [f"{len(pending)} pending prediction(s):"]
        for p in pending:
            days = p.get("_days_until_deadline", "?")
            lines.append(
                f"  [{p['prediction_id'][:8]}] {p['statement'][:60]}\n"
                f"    conf={p['confidence']} | deadline={p['deadline']} ({days}d)"
            )
        return "\n".join(lines)

    if action == "expired":
        expired = check_expired_predictions()
        if not expired:
            return "No expired predictions needing verification."
        lines = [f"{len(expired)} expired prediction(s):"]
        for p in expired:
            overdue = p.get("_days_overdue", "?")
            lines.append(
                f"  [{p['prediction_id'][:8]}] {p['statement'][:60]}\n"
                f"    conf={p['confidence']} | {overdue}d overdue"
            )
        return "\n".join(lines)

    if action == "accuracy":
        acc = get_prediction_accuracy()
        if acc["total"] == 0:
            return "No predictions yet."
        lines = [
            f"Predictions: {acc['total']} total ({acc['pending']} pending, {acc['checked']} checked)",
            f"  Correct: {acc['correct']} | Wrong: {acc['wrong']} | Partial: {acc['partially_correct']} | Expired: {acc['expired']}",
        ]
        if acc["accuracy"] is not None:
            lines.append(f"  Accuracy: {acc['accuracy']:.0%}")
        if acc["avg_confidence"] is not None:
            lines.append(f"  Avg confidence: {acc['avg_confidence']:.0%}")
        if acc["calibration"] is not None:
            cal = acc["calibration"]
            cal_label = "well-calibrated" if abs(cal) < 0.1 else ("overconfident" if cal < 0 else "underconfident")
            lines.append(f"  Calibration: {cal:+.0%} ({cal_label})")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required."
        results = search_predictions(query, n=n)
        if not results:
            return "No matching predictions."
        lines = [f"Found {len(results)} prediction(s):"]
        for p in results:
            sim = p.get("_similarity", "")
            sim_str = f" (sim={sim})" if sim else ""
            lines.append(
                f"  [{p['prediction_id'][:8]}] {p['statement'][:60]}{sim_str}\n"
                f"    conf={p['confidence']} | {p['status']} | dl={p['deadline']}"
            )
        return "\n".join(lines)

    if action == "list":
        preds = list_predictions(status=status, n=n)
        if not preds:
            return "No predictions found."
        lines = [f"{len(preds)} prediction(s):"]
        for p in preds:
            lines.append(
                f"  [{p['prediction_id'][:8]}] {p['statement'][:60]}\n"
                f"    conf={p['confidence']} | {p['status']} | dl={p['deadline']}"
            )
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: predict, check, get, pending, expired, accuracy, search, list"


@mcp.tool()
def elara_principle(
    action: str = "list",
    principle_id: Optional[str] = None,
    statement: Optional[str] = None,
    domain: Optional[str] = None,
    query: Optional[str] = None,
    confidence: Optional[float] = None,
    evidence: Optional[str] = None,
    run_date: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """
    Principles — crystallized self-derived rules from repeated insights.

    Principles emerge when the same insight appears 3+ times.
    They represent wisdom — high-level rules that guide behavior.

    Args:
        action: What to do:
            "list"      — List all principles (optional domain filter)
            "get"       — Get a single principle (needs principle_id)
            "search"    — Semantic search (needs query)
            "confirm"   — Confirm a principle (needs principle_id)
            "challenge" — Challenge a principle (needs principle_id, optional evidence)
            "create"    — Manually create (needs statement)
            "stats"     — Aggregate statistics
        principle_id: Principle ID (for get, confirm, challenge)
        statement: Principle statement (for create)
        domain: Domain filter or assignment
        query: Search query (for search)
        confidence: Initial confidence (for create)
        evidence: Challenging evidence text (for challenge)
        run_date: Overnight run date (for confirm)
        tags: Comma-separated tags (for create)

    Returns:
        Principle info, list, or stats
    """
    from daemon.principles import (
        create_principle, confirm_principle, challenge_principle,
        get_active_principles, search_principles, get_principle,
        list_principles, get_principle_stats,
    )
    from daemon.schemas import ElaraNotFoundError

    if action == "list":
        principles = list_principles(domain=domain)
        if not principles:
            return "No principles yet."
        lines = [f"{len(principles)} principle(s):"]
        for p in principles:
            confirmed = p.get("times_confirmed", 0)
            challenged = p.get("times_challenged", 0)
            lines.append(
                f"  [{p['principle_id'][:8]}] {p['statement'][:60]}\n"
                f"    {p['domain']} | conf={p['confidence']} | {p['status']} | "
                f"+{confirmed}/-{challenged}"
            )
        return "\n".join(lines)

    if action == "get":
        if not principle_id:
            return "Error: principle_id is required."
        p = get_principle(principle_id)
        if not p:
            return f"Principle {principle_id} not found."
        lines = [
            f"Principle: {p['principle_id']}",
            f"  {p['statement']}",
            f"  Domain: {p['domain']} | Status: {p['status']}",
            f"  Confidence: {p['confidence']}",
            f"  Confirmed: {p.get('times_confirmed', 0)} | Challenged: {p.get('times_challenged', 0)}",
            f"  Created: {p.get('created', '?')[:19]}",
        ]
        if p.get("last_confirmed"):
            lines.append(f"  Last confirmed: {p['last_confirmed'][:19]}")
        if p.get("source_models"):
            lines.append(f"  Source models: {', '.join(p['source_models'][:5])}")
        if p.get("tags"):
            lines.append(f"  Tags: {', '.join(p['tags'])}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required."
        results = search_principles(query, n=5)
        if not results:
            return "No matching principles."
        lines = [f"Found {len(results)} principle(s):"]
        for p in results:
            sim = p.get("_similarity", "")
            sim_str = f" (sim={sim})" if sim else ""
            lines.append(
                f"  [{p['principle_id'][:8]}] {p['statement'][:60]}{sim_str}\n"
                f"    {p['domain']} | conf={p['confidence']} | {p['status']}"
            )
        return "\n".join(lines)

    if action == "confirm":
        if not principle_id:
            return "Error: principle_id is required."
        try:
            p = confirm_principle(principle_id, run_date=run_date)
            return (
                f"Principle confirmed: {p['principle_id'][:8]}\n"
                f"  {p['statement'][:80]}\n"
                f"  Confidence: {p['confidence']} | Confirmed {p['times_confirmed']}x"
            )
        except ElaraNotFoundError as e:
            return str(e)

    if action == "challenge":
        if not principle_id:
            return "Error: principle_id is required."
        try:
            p = challenge_principle(principle_id, evidence=evidence)
            return (
                f"Principle challenged: {p['principle_id'][:8]}\n"
                f"  {p['statement'][:80]}\n"
                f"  Confidence: {p['confidence']} | Status: {p['status']} | "
                f"Challenged {p['times_challenged']}x"
            )
        except ElaraNotFoundError as e:
            return str(e)

    if action == "create":
        if not statement:
            return "Error: statement is required."
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        p = create_principle(
            statement=statement,
            domain=domain or "general",
            confidence=confidence or 0.5,
            tags=tag_list,
        )
        return (
            f"Principle created: {p['principle_id']}\n"
            f"  {p['statement'][:100]}\n"
            f"  Domain: {p['domain']} | Confidence: {p['confidence']}"
        )

    if action == "stats":
        stats = get_principle_stats()
        if stats["total"] == 0:
            return "No principles yet."
        lines = [
            f"Principles: {stats['total']} total",
            f"  By status: {stats['by_status']}",
            f"  By domain: {stats['by_domain']}",
            f"  Total confirmations: {stats['total_confirmations']}",
            f"  Total challenges: {stats['total_challenges']}",
        ]
        if stats["avg_confidence"] is not None:
            lines.append(f"  Avg confidence (active): {stats['avg_confidence']}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: list, get, search, confirm, challenge, create, stats"
