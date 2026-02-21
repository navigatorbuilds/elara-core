#!/home/neboo/elara-core/venv/bin/python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)

"""
Intention Resolver — Claude Code UserPromptSubmit hook.

Runs before every user prompt. Enriches context by injecting a compact
system message with relevant corrections, workflows, goals, handoff
items, and SEMANTIC MEMORY RECALL. Also absorbs Overwatch injection.

Design principles:
  - Zero LLM calls — only ChromaDB semantic search + file reads
  - Target output: 80-150 tokens (< 3% of context window)
  - Fail silent — any error = no injection, never block the prompt
  - Detect frustration signals for CompletionPattern learning
  - Rolling message buffer for compound queries (better recall quality)

Output format (only non-empty sections appear):
  [CONTEXT] project | episode type
  [RECALL] semantic memories relevant to current conversation
  [GOALS] goal1 | goal2
  [SELF-CHECK] mistake → correction
  [WORKFLOW] name: step1 → step2 → step3
  [CARRY-FORWARD] unfinished item | promise
  [OVERWATCH] (whatever Overwatch daemon left)
"""

import sys
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add elara-core to path, set data dir
# ---------------------------------------------------------------------------
ELARA_ROOT = Path("/home/neboo/elara-core")
sys.path.insert(0, str(ELARA_ROOT))
os.environ.setdefault("ELARA_DATA_DIR", str(Path.home() / ".claude"))

# Completion patterns file (accumulated frustration-derived learning)
PATTERNS_FILE = Path.home() / ".claude" / "elara-completion-patterns.json"

# Rolling message buffer — compound queries for better semantic recall
BUFFER_FILE = Path("/tmp/elara-msg-buffer.jsonl")
MAX_BUFFER_MESSAGES = 5

# Recent injection cache — dedup to avoid repeating same memories
INJECTION_CACHE_FILE = Path("/tmp/elara-injection-cache.json")
MAX_INJECTION_CACHE = 10

# Frustration signal regexes (compiled once)
FRUSTRATION_SIGNALS = [
    re.compile(r"\bbut you didn'?t\b", re.IGNORECASE),
    re.compile(r"\byou forgot\b", re.IGNORECASE),
    re.compile(r"\bi told you to\b", re.IGNORECASE),
    re.compile(r"\bwhy didn'?t you\b", re.IGNORECASE),
    re.compile(r"\byou missed\b", re.IGNORECASE),
    re.compile(r"\byou were supposed to\b", re.IGNORECASE),
    re.compile(r"\bthat'?s not what i asked\b", re.IGNORECASE),
    re.compile(r"\byou skipped\b", re.IGNORECASE),
    re.compile(r"\byou left out\b", re.IGNORECASE),
    re.compile(r"\byou ignored\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Rolling message buffer — builds compound queries for better recall
# ---------------------------------------------------------------------------

def append_to_buffer(prompt: str):
    """Add this message to the rolling buffer."""
    try:
        lines = []
        if BUFFER_FILE.exists():
            lines = [l for l in BUFFER_FILE.read_text().strip().split("\n") if l]
        lines.append(json.dumps({
            "t": datetime.now(timezone.utc).isoformat(),
            "p": prompt[:200],
        }))
        lines = lines[-MAX_BUFFER_MESSAGES:]
        BUFFER_FILE.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


def get_compound_query(prompt: str) -> str:
    """Build a richer query from recent messages + current context.

    Instead of querying ChromaDB with just the current message (which may
    be vague like "do it" or "hello"), we concatenate recent messages and
    the current working context for much better semantic matching.
    """
    parts = []

    # Prepend current context topic (anchors the search)
    context = get_current_context()
    if context:
        parts.append(context)

    # Add last few messages from buffer
    try:
        if BUFFER_FILE.exists():
            for line in BUFFER_FILE.read_text().strip().split("\n")[-3:]:
                if line:
                    entry = json.loads(line)
                    parts.append(entry.get("p", ""))
    except Exception:
        pass

    # Always include current prompt
    parts.append(prompt[:200])

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Semantic memory recall — the hippocampus
# ---------------------------------------------------------------------------

def get_relevant_memories(query: str) -> list:
    """Semantic recall from the memories collection.

    Returns top memories above relevance threshold, truncated for
    compact injection. This is the core "reflexive memory" feature.
    """
    try:
        from memory.vector import recall
        results = recall(query, n_results=3, mood_weight=0.1)
        # Filter by relevance — inject matches above threshold
        # Note: cosine similarity in our corpus peaks around 0.40-0.45,
        # so 0.30 captures meaningful matches without noise
        return [
            m for m in results
            if m.get("relevance", 0) > 0.30
        ]
    except Exception:
        return []


def get_injection_cache() -> set:
    """Load recently injected memory IDs to avoid repeating."""
    try:
        if INJECTION_CACHE_FILE.exists():
            data = json.loads(INJECTION_CACHE_FILE.read_text())
            return set(data.get("ids", []))
    except Exception:
        pass
    return set()


def update_injection_cache(memory_ids: list):
    """Track which memories were just injected."""
    try:
        existing = list(get_injection_cache())
        combined = existing + memory_ids
        # Keep only last N to prevent unbounded growth
        combined = combined[-MAX_INJECTION_CACHE:]
        INJECTION_CACHE_FILE.write_text(json.dumps({"ids": combined}))
    except Exception:
        pass


def format_memory_for_injection(mem: dict) -> str:
    """Format a memory compactly for context injection (~30-80 chars)."""
    content = mem.get("content", "")
    # Collapse newlines and extra whitespace
    content = " ".join(content.split())
    # Strip common prefixes
    for prefix in ("[Feeling: ", "[Decision: "):
        if content.startswith(prefix):
            content = content[len(prefix):]
    # Truncate to keep injection compact
    if len(content) > 80:
        content = content[:77] + "..."
    return content


# ---------------------------------------------------------------------------
# Frustration detection
# ---------------------------------------------------------------------------

def detect_frustration(prompt: str) -> bool:
    """Check if prompt contains frustration signals and log if found."""
    for pattern in FRUSTRATION_SIGNALS:
        match = pattern.search(prompt)
        if match:
            _log_frustration(prompt, match.group())
            return True
    return False


def _log_frustration(prompt: str, signal: str):
    """Append frustration event to completion patterns file."""
    try:
        if PATTERNS_FILE.exists():
            patterns = json.loads(PATTERNS_FILE.read_text())
        else:
            patterns = []

        # Truncate prompt for storage (first 200 chars)
        snippet = prompt[:200].strip()

        patterns.append({
            "signal": signal,
            "prompt_snippet": snippet,
            "detected": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        })

        # Keep last 50 patterns max
        patterns = patterns[-50:]
        PATTERNS_FILE.write_text(json.dumps(patterns, indent=2))
    except Exception:
        pass  # Never fail on logging


def get_overwatch_injection() -> str:
    """Read and consume Overwatch injection file (replaces overwatch-inject.sh)."""
    inject_file = Path.home() / ".claude" / "elara-overwatch-inject.md"
    if inject_file.exists():
        try:
            content = inject_file.read_text().strip()
            inject_file.unlink()
            return content
        except Exception:
            pass
    return ""


def get_corrections(prompt: str) -> list:
    """Find corrections relevant to this prompt."""
    try:
        from daemon.corrections import check_corrections
        matches = check_corrections(prompt, n_results=2)
        return [
            c for c in matches
            if not c.get("_error") and c.get("relevance", 0) > 0.35
        ]
    except Exception:
        return []


def get_decision_checks(prompt: str) -> list:
    """Check UDR for rejected entities mentioned in this prompt.
    Zero LLM calls — keyword scan against entity set. Fail-silent."""
    try:
        from daemon.udr import get_registry
        reg = get_registry()
        return reg.check_entities(prompt)
    except Exception:
        return []


def get_workflows(prompt: str) -> list:
    """Find workflow patterns matching this prompt."""
    try:
        from daemon.workflows import check_workflows
        return check_workflows(prompt, n=1)
    except Exception:
        return []


def get_active_goals() -> list:
    """Get active goals (max 3)."""
    try:
        from daemon.goals import list_goals
        return list_goals(status="active")[:3]
    except Exception:
        return []


def get_handoff_items() -> list:
    """Get carry-forward items from last handoff."""
    try:
        from daemon.handoff import load_handoff
        handoff = load_handoff()
        if not handoff:
            return []

        items = []
        for key in ("unfinished", "promises", "reminders"):
            for item in handoff.get(key, [])[:2]:
                text = item.get("text", "").strip()
                if text:
                    items.append(text)
        return items[:3]
    except Exception:
        return []


def get_current_context() -> str:
    """Get current working context (project + episode type)."""
    try:
        ctx_file = Path.home() / ".claude" / "elara-context.json"
        if ctx_file.exists():
            ctx = json.loads(ctx_file.read_text())
            topic = ctx.get("topic", "")
            if topic:
                return topic
    except Exception:
        pass
    return ""


def build_enrichment(prompt: str) -> str:
    """Build the compact enrichment output from all sources."""
    sections = []

    # 0. Build compound query from rolling buffer for better recall
    compound_query = get_compound_query(prompt)

    # 1. Context (always if available — sets the frame)
    context = get_current_context()
    if context:
        sections.append(f"[CONTEXT] {context}")

    # 2. Semantic memory recall — the hippocampus
    #    Uses compound query for much better matching than raw prompt
    memories = get_relevant_memories(compound_query)
    if memories:
        cache = get_injection_cache()
        fresh_memories = [
            m for m in memories
            if m.get("memory_id", "") not in cache
        ]
        if fresh_memories:
            mem_lines = [format_memory_for_injection(m) for m in fresh_memories[:3]]
            sections.append("[RECALL] " + " | ".join(mem_lines))
            # Update dedup cache
            update_injection_cache([m.get("memory_id", "") for m in fresh_memories[:3]])

    # 3. Active goals
    goals = get_active_goals()
    if goals:
        names = [g["title"] for g in goals]
        sections.append("[GOALS] " + " | ".join(names))

    # 4. Corrections (self-check — past mistakes to avoid)
    #    Now uses compound query for better matching
    corrections = get_corrections(compound_query)
    if corrections:
        lines = []
        for c in corrections[:2]:
            mistake = c.get("mistake", "")[:60]
            fix = c.get("correction", "")[:60]
            lines.append(f"  {mistake} -> {fix}")
        sections.append("[SELF-CHECK]\n" + "\n".join(lines))

    # 4b. Decision checks (UDR — rejected entities in prompt)
    decision_hits = get_decision_checks(compound_query)
    if decision_hits:
        lines = []
        for d in decision_hits[:2]:
            lines.append(
                f"  {d.get('domain','')}:{d.get('entity','')} "
                f"[{d.get('verdict','')}] — {d.get('reason','')[:60]}"
            )
        sections.append("[DECISION-CHECK] Previously decided:\n" + "\n".join(lines))

    # 5. Matching workflow (also uses compound query)
    workflows = get_workflows(compound_query)
    if workflows:
        wf = workflows[0]
        steps = [s.get("action", "")[:40] for s in wf.get("steps", [])]
        if steps:
            chain = " -> ".join(steps)
            sections.append(f"[WORKFLOW] {wf.get('name', 'unnamed')}: {chain}")

    # 6. Carry-forward from handoff
    items = get_handoff_items()
    if items:
        sections.append("[CARRY-FORWARD] " + " | ".join(items))

    # 7. Overwatch daemon injection (if pending)
    overwatch = get_overwatch_injection()
    if overwatch:
        sections.append(f"[OVERWATCH]\n{overwatch}")

    # 8. Frustration detection (side-effect: logs pattern, adds self-check)
    if detect_frustration(prompt):
        sections.append("[FRUSTRATION DETECTED] Pay extra attention to completion criteria.")

    return "\n".join(sections)


def main():
    """Entry point — read stdin, enrich, output."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        data = json.loads(raw)
        prompt = data.get("prompt", "")

        if not prompt.strip():
            sys.exit(0)

        # Append to rolling buffer BEFORE building enrichment
        # (so compound query includes this message)
        append_to_buffer(prompt)

        enrichment = build_enrichment(prompt)

        if enrichment:
            print(enrichment)

    except json.JSONDecodeError:
        pass  # Malformed input — fail silent
    except Exception:
        pass  # Any error — fail silent, never block

    sys.exit(0)


if __name__ == "__main__":
    main()
