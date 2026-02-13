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
                   problems: List[str] = None) -> Path:
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
               research_queries: int = 0, status: str = "completed") -> Path:
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
    path = d / "meta.json"
    path.write_text(json.dumps(data, indent=2))
    logger.info("Meta written → %s", path.name)
    return path
