# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight output — write round results, findings, and metadata.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from core.paths import get_paths
from daemon.overnight.config import today_dir, LATEST_FINDINGS

logger = logging.getLogger("elara.overnight")


def write_round(round_num: int, phase_name: str, phase_title: str,
                output: str, research: str = "", duration_s: float = 0) -> Path:
    """Save a single round's output as JSON."""
    d = today_dir()
    data = {
        "round": round_num,
        "phase": phase_name,
        "title": phase_title,
        "output": output,
        "research": research,
        "duration_seconds": round(duration_s, 1),
        "timestamp": datetime.now().isoformat(),
    }
    path = d / f"round-{round_num:02d}.json"
    path.write_text(json.dumps(data, indent=2))
    logger.info("  Saved round %d → %s", round_num, path.name)
    return path


def write_findings(rounds: List[Dict[str, Any]], mode: str = "exploratory",
                   problems: List[str] = None,
                   cognition_summary: Dict[str, Any] = None) -> Path:
    """
    Generate findings.md from all rounds.

    Structure: synthesis/recommendation first, then individual round details.
    """
    d = today_dir()
    lines = []

    lines.append(f"# Overnight Findings — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*Mode: {mode}*")
    lines.append(f"*Rounds: {len(rounds)}*")
    lines.append("")

    # Find the synthesis/final round and put it first
    synthesis_round = None
    other_rounds = []
    for r in rounds:
        if r.get("phase") in ("synthesis", "synthesize"):
            synthesis_round = r
        else:
            other_rounds.append(r)

    if synthesis_round:
        lines.append("---")
        lines.append("")
        lines.append(f"## {synthesis_round.get('title', 'Synthesis')}")
        lines.append("")
        lines.append(synthesis_round.get("output", ""))
        lines.append("")

    # Directed mode — group by problem
    if mode == "directed" and problems:
        lines.append("---")
        lines.append("")
        rounds_per_problem = len(other_rounds) // max(len(problems), 1)
        for i, problem in enumerate(problems):
            lines.append(f"## Problem: {problem[:100]}")
            lines.append("")
            start = i * rounds_per_problem
            end = start + rounds_per_problem
            for r in other_rounds[start:end]:
                if r.get("phase") != "synthesize":
                    lines.append(f"### {r.get('title', r.get('phase', 'Round'))}")
                    lines.append("")
                    lines.append(r.get("output", ""))
                    lines.append("")

    # Exploratory mode — all rounds in order
    elif other_rounds:
        lines.append("---")
        lines.append("")
        lines.append("## Detailed Analysis")
        lines.append("")
        for r in other_rounds:
            lines.append(f"### {r.get('title', r.get('phase', 'Round'))}")
            lines.append("")
            lines.append(r.get("output", ""))
            lines.append("")

    # 3D Cognition Updates section
    if cognition_summary and any(v for k, v in cognition_summary.items() if k != "parse_failures"):
        lines.append("---")
        lines.append("")
        lines.append("## 3D Cognition Updates")
        lines.append("")
        cs = cognition_summary
        if cs.get("models_created"):
            lines.append(f"- **Models created:** {cs['models_created']}")
        if cs.get("models_updated"):
            lines.append(f"- **Models updated:** {cs['models_updated']}")
        if cs.get("models_checked"):
            lines.append(f"- **Models checked:** {cs['models_checked']}")
        if cs.get("models_decayed"):
            lines.append(f"- **Models decayed (age):** {cs['models_decayed']}")
        if cs.get("predictions_created"):
            lines.append(f"- **Predictions made:** {cs['predictions_created']}")
        if cs.get("predictions_checked"):
            lines.append(f"- **Predictions verified:** {cs['predictions_checked']}")
        if cs.get("principles_created"):
            lines.append(f"- **Principles crystallized:** {cs['principles_created']}")
        if cs.get("principles_confirmed"):
            lines.append(f"- **Principles confirmed:** {cs['principles_confirmed']}")
        if cs.get("parse_failures"):
            lines.append(f"- **Parse failures:** {cs['parse_failures']}")
        if cs.get("memory_consolidated"):
            lines.append("")
            lines.append("### Memory Consolidation")
            if cs.get("memories_merged"):
                lines.append(f"- **Memories merged:** {cs['memories_merged']}")
            if cs.get("memories_archived"):
                lines.append(f"- **Memories archived:** {cs['memories_archived']}")
            if cs.get("memories_strengthened"):
                lines.append(f"- **Memories strengthened:** {cs['memories_strengthened']}")
            if cs.get("memories_decayed"):
                lines.append(f"- **Memories decayed:** {cs['memories_decayed']}")
            if cs.get("contradictions_found"):
                lines.append(f"- **Contradictions detected:** {cs['contradictions_found']}")
            if cs.get("memories_remaining"):
                lines.append(f"- **Memories remaining:** {cs['memories_remaining']}")
        lines.append("")

    content = "\n".join(lines)
    path = d / "findings.md"
    path.write_text(content)
    logger.info("Findings written → %s (%d chars)", path.name, len(content))

    # Copy to latest
    try:
        shutil.copy2(str(path), str(LATEST_FINDINGS))
        logger.info("Latest findings → %s", LATEST_FINDINGS.name)
    except OSError as e:
        logger.warning("Failed to copy to latest: %s", e)

    return path


def write_meta(started: datetime, config: dict, mode: str,
               rounds_completed: int, problems_processed: int = 0,
               research_queries: int = 0, status: str = "completed",
               cognition_3d: Dict[str, Any] = None) -> Path:
    """Write run metadata."""
    d = today_dir()
    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "started": started.isoformat(),
        "ended": datetime.now().isoformat(),
        "mode": mode,
        "rounds_completed": rounds_completed,
        "problems_processed": problems_processed,
        "research_queries": research_queries,
        "status": status,
        "config": config,
    }
    if cognition_3d:
        data["cognition_3d"] = cognition_3d
    path = d / "meta.json"
    path.write_text(json.dumps(data, indent=2))
    logger.info("Meta written → %s", path.name)
    return path


def write_morning_brief(
    rounds: List[Dict[str, Any]],
    cognition_summary: Dict[str, Any] = None,
    drift_rounds: List[Dict[str, Any]] = None,
) -> Path:
    """
    Write a concise morning brief — what matters when you wake up.

    Reads handoff for session context, pulls TL;DR from synthesis,
    lists prediction deadlines and new models.
    """
    _p = get_paths()
    lines = []
    lines.append(f"# Morning Brief — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Extract TL;DR from synthesis round
    for r in rounds:
        if r.get("phase") in ("synthesis", "synthesize"):
            output = r.get("output", "")
            # Try to extract just the TL;DR section
            tldr_start = output.find("TL;DR")
            if tldr_start == -1:
                tldr_start = output.find("**TL;DR**")
            if tldr_start != -1:
                # Take up to the next ## heading or 500 chars
                tldr_text = output[tldr_start:tldr_start + 500]
                next_heading = tldr_text.find("\n##", 10)
                next_heading2 = tldr_text.find("\n**Key", 10)
                end = min(
                    next_heading if next_heading != -1 else 500,
                    next_heading2 if next_heading2 != -1 else 500,
                )
                lines.append(tldr_text[:end].strip())
            else:
                # No TL;DR marker, take first 300 chars
                lines.append(output[:300].strip())
            lines.append("")
            break

    # Prediction deadlines (from handoff or predictions module)
    try:
        from daemon.predictions import get_pending_predictions, check_expired_predictions
        expired = check_expired_predictions()
        pending = get_pending_predictions(days_ahead=7)
        if expired or pending:
            lines.append("## Predictions")
            for p in expired[:3]:
                lines.append(f"- **OVERDUE ({p.get('_days_overdue', '?')}d):** {p.get('statement', '?')[:80]}")
            for p in pending[:5]:
                lines.append(f"- [{p.get('_days_until_deadline', '?')}d] {p.get('statement', '?')[:80]} (conf={p.get('confidence', '?')})")
            lines.append("")
    except Exception:
        pass

    # 3D cognition summary
    if cognition_summary and any(v for k, v in cognition_summary.items() if k != "parse_failures"):
        lines.append("## Overnight Brain Activity")
        cs = cognition_summary
        parts = []
        if cs.get("models_created"):
            parts.append(f"{cs['models_created']} new models")
        if cs.get("models_updated"):
            parts.append(f"{cs['models_updated']} models updated")
        if cs.get("predictions_created"):
            parts.append(f"{cs['predictions_created']} new predictions")
        if cs.get("predictions_checked"):
            parts.append(f"{cs['predictions_checked']} predictions verified")
        if cs.get("principles_created"):
            parts.append(f"{cs['principles_created']} principles crystallized")
        if cs.get("principles_confirmed"):
            parts.append(f"{cs['principles_confirmed']} principles confirmed")
        if parts:
            lines.append(", ".join(parts))
        lines.append("")

    # Handoff context (what was the user doing?)
    try:
        handoff_path = _p.handoff_file
        if handoff_path.exists():
            handoff = json.loads(handoff_path.read_text())
            mood = handoff.get("mood_and_mode", "")
            if mood:
                lines.append(f"## Last Session Mood")
                lines.append(mood)
                lines.append("")
            plans = handoff.get("next_plans", [])
            if plans:
                lines.append("## Planned Next")
                for p in plans[:5]:
                    text = p.get("text", str(p)) if isinstance(p, dict) else str(p)
                    lines.append(f"- {text[:80]}")
                lines.append("")
    except (json.JSONDecodeError, OSError):
        pass

    # Drift highlight (one-liner from best drift output)
    if drift_rounds:
        lines.append("## Overnight Doodle")
        # Pick the longest output as "most interesting" heuristic
        best = max(drift_rounds, key=lambda r: len(r.get("output", "")))
        first_line = best.get("output", "").strip().split("\n")[0][:200]
        lines.append(f"*{best.get('title', 'Drift')}:* {first_line}")
        lines.append("")

    content = "\n".join(lines)
    brief_path = _p.morning_brief
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(content)
    logger.info("Morning brief written → %s (%d chars)", brief_path.name, len(content))
    return brief_path


def write_creative_journal(
    drift_rounds: List[Dict[str, Any]],
) -> Path:
    """
    Append drift outputs to the creative journal.

    Unlike findings (overwritten daily), the journal ACCUMULATES.
    Each entry is dated and attributed to its technique.
    """
    _p = get_paths()
    journal_path = _p.creative_journal
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    # Build new entry
    lines = []
    lines.append(f"\n---\n")
    lines.append(f"## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Drift Session")
    lines.append("")

    for r in drift_rounds:
        technique = r.get("title", r.get("technique", "Unknown"))
        output = r.get("output", "").strip()
        items = r.get("items", [])

        lines.append(f"### {technique}")
        if items:
            seeds = ", ".join(f"[{i['category']}]" for i in items)
            lines.append(f"*Seeds: {seeds}*")
        lines.append("")
        lines.append(output)
        lines.append("")

    entry = "\n".join(lines)

    # Append (not overwrite)
    if journal_path.exists():
        existing = journal_path.read_text()
    else:
        existing = "# Elara's Creative Journal\n\n*Overnight drift sessions — the 5% that matters.*\n"

    journal_path.write_text(existing + entry)
    logger.info("Creative journal updated → %s (+%d chars)", journal_path.name, len(entry))

    # Also save a copy in today's dir
    today_copy = today_dir() / "drift.md"
    today_copy.write_text("\n".join(lines))

    return journal_path
