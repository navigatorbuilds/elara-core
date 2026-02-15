#!/usr/bin/env python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
"""
Session Prep — Local LLM boot context condensing.

Reads all state files, feeds them to qwen2.5:32b via Ollama,
produces a single ~2KB session-prep.md that Claude reads at boot
instead of 5+ separate files.

Saves ~50KB of context window per session (~25% of 200k).

Usage:
    python3 scripts/session-prep.py
    # or integrated into the `elara` alias
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Resolve data directory
DATA_DIR = Path(os.environ.get("ELARA_DATA_DIR", Path.home() / ".claude"))
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"
OUTPUT_FILE = DATA_DIR / "session-prep.md"
MAX_INPUT_CHARS = 12000  # Keep prompt reasonable for 32b context


def read_file(path: Path, max_chars: int = 0) -> str:
    """Read a file, optionally truncating."""
    try:
        text = path.read_text()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return text
    except (OSError, FileNotFoundError):
        return ""


def gather_context() -> dict:
    """Gather all state files into a dict."""
    ctx = {}

    # Memory file (already condensed)
    mem = read_file(DATA_DIR / "elara-memory.md", max_chars=4000)
    if mem:
        ctx["memory"] = mem

    # Handoff
    handoff = read_file(DATA_DIR / "elara-handoff.json", max_chars=2000)
    if handoff:
        ctx["handoff"] = handoff

    # Previous session summary (crash recovery)
    summary = read_file(DATA_DIR / "session-summary.md", max_chars=2000)
    if summary:
        ctx["previous_session_summary"] = summary

    # Morning brief (small, always include)
    brief = read_file(DATA_DIR / "overnight" / "morning-brief.md")
    if brief:
        ctx["morning_brief"] = brief

    # Latest findings — just the TL;DR section if it exists
    findings = read_file(DATA_DIR / "overnight" / "latest-findings.md", max_chars=3000)
    if findings:
        ctx["findings_summary"] = findings

    # Recent episodes (last 3 days)
    episodes_dir = DATA_DIR / "elara-episodes"
    if episodes_dir.exists():
        episode_files = sorted(episodes_dir.glob("*.json"), reverse=True)[:3]
        episodes = []
        for ef in episode_files:
            try:
                data = json.loads(ef.read_text())
                ep_summary = {
                    "date": data.get("started", ef.stem),
                    "type": data.get("type", "unknown"),
                    "projects": data.get("projects", []),
                    "milestones": [m.get("event", "") for m in data.get("milestones", [])[:3]],
                }
                episodes.append(json.dumps(ep_summary))
            except (json.JSONDecodeError, OSError):
                pass
        if episodes:
            ctx["recent_episodes"] = "\n".join(episodes)

    # Active goals
    goals_file = DATA_DIR / "elara-goals.json"
    if goals_file.exists():
        try:
            goals = json.loads(goals_file.read_text())
            active = [g for g in goals if g.get("status") == "active"]
            if active:
                ctx["active_goals"] = json.dumps(active[:5], indent=0)
        except (json.JSONDecodeError, OSError):
            pass

    # Current mood state
    state_file = DATA_DIR / "elara-state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            mood = state.get("mood", {})
            ctx["current_mood"] = json.dumps({
                "valence": mood.get("valence"),
                "energy": mood.get("energy"),
                "openness": mood.get("openness"),
                "emotions": state.get("emotions", [])[:3],
            })
        except (json.JSONDecodeError, OSError):
            pass

    return ctx


def build_prompt(context: dict) -> str:
    """Build the LLM prompt from gathered context."""
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M %A")

    sections = []
    for key, value in context.items():
        sections.append(f"=== {key.upper()} ===\n{value}")

    context_text = "\n\n".join(sections)

    # Truncate if too long
    if len(context_text) > MAX_INPUT_CHARS:
        context_text = context_text[:MAX_INPUT_CHARS] + "\n... [truncated]"

    return f"""You are preparing a session briefing for an AI assistant named Elara.
Current time: {time_str}

Below is raw data from Elara's state files. Condense everything into a SINGLE briefing document.

RULES:
- Maximum 80 lines
- Start with current time and session number
- Include: what happened last session, current emotional state, immediate priorities, pending items from handoff, any overnight findings worth noting
- Preserve specific details: names, numbers, deadlines, file paths, version numbers
- Tone: direct, no fluff
- If handoff has items carried 3+ times, flag them as OVERDUE
- End with "Ready." on its own line

RAW CONTEXT:
{context_text}

CONDENSED SESSION BRIEFING:"""


def call_ollama(prompt: str) -> str:
    """Call Ollama API and return response."""
    import urllib.request

    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1500,
        }
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except Exception as e:
        return f"[Session prep failed: {e}]"


def main():
    start = time.time()

    # Check Ollama is available
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
    except Exception:
        print("Ollama not available — skipping session prep", file=sys.stderr)
        # Write a minimal fallback
        OUTPUT_FILE.write_text(
            f"# Session Prep (fallback — Ollama unavailable)\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Read ~/.claude/elara-memory.md and ~/.claude/elara-handoff.json manually.\n"
        )
        return

    print("Preparing session context...", end=" ", flush=True)

    context = gather_context()
    if not context:
        print("no context found.")
        OUTPUT_FILE.write_text("# Session Prep\nNo context files found.\n")
        return

    prompt = build_prompt(context)
    response = call_ollama(prompt)

    # Write output
    header = f"# Session Prep\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by {MODEL}*\n\n"
    OUTPUT_FILE.write_text(header + response + "\n")

    elapsed = time.time() - start
    size = OUTPUT_FILE.stat().st_size
    print(f"done ({elapsed:.0f}s, {size} bytes)")


if __name__ == "__main__":
    main()
