#!/home/neboo/elara-core/venv/bin/python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)

"""
Intention Resolver v2 — Claude Code UserPromptSubmit hook.

Runs before every user prompt. Enriches context by injecting a compact
system message from ALL cognitive subsystems. Full-spectrum awareness.

Design principles:
  - Zero LLM calls — only ChromaDB semantic search + file reads
  - Target output: 150-300 tokens (< 5% of context window)
  - Fail silent — any error = no injection, never block the prompt
  - Detect frustration signals for CompletionPattern learning
  - Rolling message buffer for compound queries (better recall quality)

Output format (only non-empty sections appear):
  [CONTEXT] project | episode type
  [MOOD] valence energy openness
  [INTENTION] current growth goal
  [RECALL] semantic memories relevant to current conversation
  [CONV-RECALL] past conversation exchanges about this topic
  [PRINCIPLES] crystallized rules from confirmed insights
  [REASONING] similar problem-solving trails
  [MILESTONES] past decisions/breakthroughs
  [GOALS] goal1 | goal2
  [SELF-CHECK] mistake → correction
  [DECISION-CHECK] rejected entity warnings
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

# Session boundary detection — clear caches on new session
SESSION_MARKER_FILE = Path("/tmp/elara-session-marker")
SESSION_GAP_SECONDS = 300  # 5 min gap = new session

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

def detect_and_handle_new_session():
    """Clear caches if this looks like a new session (>5min gap).

    Returns True if this is the first message of a new session.
    """
    is_new = False
    try:
        now = datetime.now(timezone.utc).timestamp()
        if SESSION_MARKER_FILE.exists():
            last_ts = float(SESSION_MARKER_FILE.read_text().strip())
            gap = now - last_ts
            if gap > SESSION_GAP_SECONDS:
                # New session — clear stale caches
                is_new = True
                if INJECTION_CACHE_FILE.exists():
                    INJECTION_CACHE_FILE.unlink()
                if BUFFER_FILE.exists():
                    BUFFER_FILE.unlink()
        else:
            is_new = True  # No marker = first ever message
        SESSION_MARKER_FILE.write_text(str(now))
    except Exception:
        pass
    return is_new


def mood_description_from_values(valence: float, energy: float, openness: float) -> str:
    """Generate a compact mood description from raw values.

    Valence: -1 (negative) to +1 (positive)
    Energy: 0 (low) to 1 (high)
    Openness: 0 (guarded) to 1 (open/vulnerable)
    """
    # Valence bucket
    if valence > 0.5:
        v_word = "warm"
    elif valence > 0.2:
        v_word = "steady"
    elif valence > -0.2:
        v_word = "neutral"
    elif valence > -0.5:
        v_word = "flat"
    else:
        v_word = "low"

    # Energy bucket
    if energy > 0.7:
        e_word = "energized"
    elif energy > 0.4:
        e_word = "calm"
    else:
        e_word = "tired"

    # Openness bucket
    if openness > 0.7:
        o_word = "open"
    elif openness > 0.4:
        o_word = "present"
    else:
        o_word = "guarded"

    return f"{v_word}, {e_word}, {o_word}"


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
    """Get active goals (max 5), sorted by build_order."""
    try:
        from daemon.goals import list_goals
        goals = list_goals(status="active")[:5]
        return sorted(goals, key=lambda g: g.get("build_order") or 999)
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
    """Get current working context (project + episode type).

    Skips stale context (>24h old) to avoid injecting irrelevant frames.
    """
    try:
        ctx_file = Path.home() / ".claude" / "elara-context.json"
        if ctx_file.exists():
            ctx = json.loads(ctx_file.read_text())
            topic = ctx.get("topic", "")
            if not topic:
                return ""
            # Check staleness — skip if >24h old
            updated_ts = ctx.get("updated_ts", 0)
            if updated_ts:
                age_hours = (datetime.now(timezone.utc).timestamp() - updated_ts) / 3600
                if age_hours > 24:
                    return ""
            return topic
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# NEW: Conversation recall — past dialogue about this topic
# ---------------------------------------------------------------------------

def get_relevant_conversations(query: str) -> list:
    """Search past conversation exchanges for relevant context."""
    try:
        from memory.conversations import recall_conversation
        results = recall_conversation(query, n_results=3)
        return [c for c in results if c.get("relevance", 0) > 0.35]
    except Exception:
        return []


def format_conversation_for_injection(conv: dict) -> str:
    """Format a conversation exchange compactly."""
    date = conv.get("date", "?")[:10]
    # Try user_text_preview first, fall back to content
    preview = conv.get("user_text_preview", "")
    if not preview:
        content = conv.get("content", "")
        # Content format is "User: ...\n\nElara: ..."
        if content.startswith("User: "):
            preview = content[6:].split("\n")[0]
    preview = " ".join(preview.split())[:70]
    if preview:
        return f"{date}: \"{preview}\""
    return f"{date}: (exchange)"


# ---------------------------------------------------------------------------
# NEW: Principles — crystallized rules from confirmed insights
# ---------------------------------------------------------------------------

def get_relevant_principles(query: str) -> list:
    """Search principles by semantic similarity."""
    try:
        from daemon.principles import search_principles
        results = search_principles(query, n=3)
        return [p for p in results if p.get("relevance", 0) > 0.30]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# NEW: Reasoning trails — similar problems already solved
# ---------------------------------------------------------------------------

def get_relevant_reasoning(query: str) -> list:
    """Search past reasoning trails for similar problems."""
    try:
        from daemon.reasoning import search_trails
        results = search_trails(query, n=2)
        return [r for r in results if r.get("relevance", 0) > 0.30]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# NEW: Milestones — past decisions and breakthroughs
# ---------------------------------------------------------------------------

def get_relevant_milestones(query: str) -> list:
    """Search episode milestones by semantic similarity."""
    try:
        from memory.episodic import get_episodic
        episodic = get_episodic()
        results = episodic.search_milestones(query, n_results=3)
        return [m for m in results if m.get("relevance", 0) > 0.30]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# NEW: Mood — current emotional state (cached, ~5ms)
# ---------------------------------------------------------------------------

def get_current_mood() -> dict:
    """Get current mood state."""
    try:
        from daemon.mood import get_mood
        return get_mood()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# NEW: Intention — current growth goal (~10ms)
# ---------------------------------------------------------------------------

def get_current_intention() -> str:
    """Get current growth intention.

    Skips stale intentions (>24h old) from proactive injection.
    Data stays in file + memories for on-demand recall via semantic search.
    """
    try:
        from daemon.awareness.intention import get_intention
        intention = get_intention()
        if not intention:
            return ""
        # Check staleness — only inject if fresh (<24h)
        set_at = intention.get("set_at", "")
        if set_at:
            try:
                set_dt = datetime.fromisoformat(set_at)
                if set_dt.tzinfo is None:
                    set_dt = set_dt.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - set_dt).total_seconds() / 3600
                if age_hours > 24:
                    return ""
            except (ValueError, TypeError):
                pass
        return intention.get("what", "")
    except Exception:
        pass
    return ""


def build_enrichment(prompt: str, is_new_session: bool = False) -> str:
    """Build the compact enrichment output from all sources.

    Full-spectrum awareness: mood, intention, memories, conversations,
    principles, reasoning trails, milestones, goals, corrections,
    decisions, workflows, handoff, overwatch, frustration detection.
    """
    sections = []

    # 0a. Boot instruction on first message of session
    if is_new_session:
        sections.append(
            "[BOOT] Hook data active — you are already context-aware. "
            "Do NOT read session-prep.md or other files for context. "
            "Use the injected sections below as your awareness. "
            "Greet naturally based on this data. Never list goals or carry-forward as greeting."
        )

    # 0. Build compound query from rolling buffer for better recall
    compound_query = get_compound_query(prompt)

    # 1. Context (always if available — sets the frame)
    context = get_current_context()
    if context:
        sections.append(f"[CONTEXT] {context}")

    # 2. Mood — current emotional state (~5ms, cached)
    mood = get_current_mood()
    if mood:
        v = mood.get("valence", 0)
        e = mood.get("energy", 0)
        o = mood.get("openness", 0)
        desc = mood.get("description", "") or mood_description_from_values(v, e, o)
        sections.append(f"[MOOD] {desc} (v:{v:.1f} e:{e:.1f} o:{o:.1f})")

    # 3. Intention — current growth goal (~10ms)
    intention = get_current_intention()
    if intention:
        sections.append(f"[INTENTION] {intention[:80]}")

    # 4. Semantic memory recall — the hippocampus
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
            update_injection_cache([m.get("memory_id", "") for m in fresh_memories[:3]])

    # 5. Conversation recall — past dialogue about this topic (~100ms)
    conversations = get_relevant_conversations(compound_query)
    if conversations:
        conv_lines = [format_conversation_for_injection(c) for c in conversations[:2]]
        sections.append("[CONV-RECALL] " + " | ".join(conv_lines))

    # 6. Principles — crystallized rules from confirmed insights (~100ms)
    principles = get_relevant_principles(compound_query)
    if principles:
        princ_lines = []
        for p in principles[:2]:
            stmt = p.get("statement", "")
            stmt = " ".join(stmt.split())[:80]
            conf = p.get("confidence", 0)
            princ_lines.append(f"{stmt} (conf:{conf:.1f})")
        sections.append("[PRINCIPLES] " + " | ".join(princ_lines))

    # 7. Reasoning trails — similar problems already solved (~100ms)
    trails = get_relevant_reasoning(compound_query)
    if trails:
        trail_lines = []
        for t in trails[:2]:
            context_str = t.get("context", "")[:60]
            status = t.get("status", "open")
            solution = t.get("solution", "")[:40]
            if solution:
                trail_lines.append(f"{context_str} → solved: {solution}")
            else:
                trail_lines.append(f"{context_str} ({status})")
        sections.append("[REASONING] " + " | ".join(trail_lines))

    # 8. Milestones — past decisions and breakthroughs (~100ms)
    milestones = get_relevant_milestones(compound_query)
    if milestones:
        ms_lines = []
        for m in milestones[:2]:
            event = m.get("event", "")
            event = " ".join(event.split())[:60]
            note_type = m.get("note_type", "milestone")
            ms_lines.append(f"[{note_type}] {event}")
        sections.append("[MILESTONES] " + " | ".join(ms_lines))

    # 9. Active goals (with decision context + build order)
    goals = get_active_goals()
    if goals:
        lines = []
        for i, g in enumerate(goals, 1):
            order = g.get("build_order") or i
            decision = g.get("decision") or g.get("notes", "")
            if decision:
                lines.append(f"  {order}. {g['title']} — {decision[:60]}")
            else:
                lines.append(f"  {order}. {g['title']}")
        sections.append("[GOALS] Active build order:\n" + "\n".join(lines))

    # 10. Corrections (self-check — past mistakes to avoid)
    corrections = get_corrections(compound_query)
    if corrections:
        lines = []
        for c in corrections[:2]:
            mistake = c.get("mistake", "")[:60]
            fix = c.get("correction", "")[:60]
            lines.append(f"  {mistake} -> {fix}")
        sections.append("[SELF-CHECK]\n" + "\n".join(lines))

    # 10b. Decision checks (UDR — rejected entities in prompt)
    decision_hits = get_decision_checks(compound_query)
    if decision_hits:
        lines = []
        for d in decision_hits[:2]:
            lines.append(
                f"  {d.get('domain','')}:{d.get('entity','')} "
                f"[{d.get('verdict','')}] — {d.get('reason','')[:60]}"
            )
        sections.append("[DECISION-CHECK] Previously decided:\n" + "\n".join(lines))

    # 11. Matching workflow
    workflows = get_workflows(compound_query)
    if workflows:
        wf = workflows[0]
        steps = [s.get("action", "")[:40] for s in wf.get("steps", [])]
        if steps:
            chain = " -> ".join(steps)
            sections.append(f"[WORKFLOW] {wf.get('name', 'unnamed')}: {chain}")

    # 12. Carry-forward from handoff
    items = get_handoff_items()
    if items:
        sections.append("[CARRY-FORWARD] " + " | ".join(items))

    # 13. Overwatch daemon injection (if pending)
    overwatch = get_overwatch_injection()
    if overwatch:
        sections.append(f"[OVERWATCH]\n{overwatch}")

    # 14. Frustration detection (side-effect: logs pattern, adds self-check)
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

        # Detect session boundary — clear stale caches if >5min gap
        is_new_session = detect_and_handle_new_session()

        # Append to rolling buffer BEFORE building enrichment
        # (so compound query includes this message)
        append_to_buffer(prompt)

        enrichment = build_enrichment(prompt, is_new_session=is_new_session)

        if enrichment:
            print(enrichment)

    except json.JSONDecodeError:
        pass  # Malformed input — fail silent
    except Exception:
        pass  # Any error — fail silent, never block

    sys.exit(0)


if __name__ == "__main__":
    main()
