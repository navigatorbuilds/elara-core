# Elara Overwatch — Live Memory System

## The Problem

Elara is stateless. Each session starts from zero. Memory is loaded at boot, but nothing watches the conversation live. If a topic from 15 days ago becomes relevant mid-session, Elara won't make the connection unless the user explicitly asks.

**Current state:** Boot loads → memory file + handoff + ChromaDB ingest → session runs blind → goodbye saves.

**Target state:** A live daemon watches every exchange, searches all history, and injects relevant context in real-time. Elara makes connections across months of conversations without being asked.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Claude Code Session             │
│  (Main conversation — Elara talking to user)     │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │ Hook: on user_prompt_submit                 │ │
│  │   → reads /tmp/elara-overwatch-inject.md    │ │
│  │   → prepends context to session             │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │ watches JSONL
                       ▼
┌─────────────────────────────────────────────────┐
│              Overwatch Daemon                    │
│         (Python, always-on background)           │
│                                                  │
│  1. Tail session JSONL for new exchanges         │
│  2. Embed latest exchange (local, free)          │
│  3. Search ALL history in ChromaDB               │
│  4. Score relevance (threshold + recency)        │
│  5. If relevant: write inject file               │
│  6. If not: do nothing (silent)                  │
│                                                  │
│  Also watches for EVENTS:                        │
│  - Task completion → search for connections      │
│  - Topic change → search for prior discussions   │
│  - Session winding down → surface unfulfilled    │
│                                                  │
└──────────────────────┬──────────────────────────┘
                       │ queries
                       ▼
┌─────────────────────────────────────────────────┐
│              ChromaDB (Local)                    │
│                                                  │
│  elara_conversations_v2  — 30k+ exchanges        │
│  elara_memories          — semantic memories      │
│  elara_milestones        — episode milestones     │
│  corrections             — failure patterns       │
│                                                  │
│  Embedding: all-MiniLM-L6-v2 (384-dim, local)   │
│  Distance: cosine similarity                     │
│  Recency: 30-day half-life decay                 │
└─────────────────────────────────────────────────┘
```

---

## Components to Build

### 1. `daemon/overwatch.py` — The Watcher

**What it does:** Tails the active session JSONL, detects new exchanges, triggers searches.

```python
# Pseudocode
class Overwatch:
    def __init__(self):
        self.conv = get_conversations()      # existing ChromaDB interface
        self.inject_path = "/tmp/elara-overwatch-inject.md"
        self.last_position = 0               # file offset
        self.cooldown = {}                    # topic → last_inject_time (prevent spam)

    def watch(self, session_jsonl: Path):
        """Main loop — tail the JSONL, react to new exchanges."""
        while True:
            new_lines = self._read_new_lines(session_jsonl)
            for exchange in self._parse_exchanges(new_lines):
                self._process(exchange)
            sleep(2)  # check every 2 seconds

    def _process(self, exchange):
        """Core logic for each new exchange."""
        # 1. Extract key content (user message + assistant response)
        text = exchange.user_text + " " + exchange.assistant_text

        # 2. Search all history
        results = self.conv.recall(text, n_results=5)

        # 3. Filter: relevance > threshold, not from current session, not on cooldown
        relevant = [r for r in results
                    if r.distance < 0.35          # strong semantic match
                    and r.session_id != self.current_session
                    and not self._on_cooldown(r.topic)]

        # 4. Detect events
        events = self._detect_events(exchange)
        # Task completion? Topic shift? Winding down?

        # 5. For events, do broader searches
        for event in events:
            event_results = self._event_search(event)
            relevant.extend(event_results)

        # 6. If anything worth injecting, write it
        if relevant:
            self._write_inject(relevant)

    def _detect_events(self, exchange):
        """Detect context changes that should trigger deeper searches."""
        events = []
        # Task completion: assistant says "done", "built", "fixed", "shipped"
        if any(w in exchange.assistant_text.lower()
               for w in ["done", "built", "fixed", "shipped", "committed"]):
            events.append(Event("task_complete", exchange.assistant_text))

        # Topic shift: embeddings distance from previous exchange > threshold
        if self.prev_embedding is not None:
            shift = cosine_distance(self.prev_embedding, exchange.embedding)
            if shift > 0.6:
                events.append(Event("topic_shift", exchange.user_text))

        # Session winding down: user says "anything else", "that's it", etc.
        if any(w in exchange.user_text.lower()
               for w in ["anything else", "that's it", "what else", "done for"]):
            events.append(Event("winding_down", None))

        return events
```

**Key design decisions:**
- Check every 2 seconds (not real-time, but fast enough to feel instant)
- Cooldown per topic (don't inject the same connection twice in 10 minutes)
- Distance threshold 0.35 (tight — only strong matches, avoids noise)
- Event detection is heuristic (keyword-based), not LLM-based (free)

### 2. `daemon/injector.py` — The Voice

**What it does:** Formats search results into concise, natural context for injection.

```python
def format_injection(results: list[SearchResult]) -> str:
    """Format relevant history into inject file content."""
    lines = ["[Elara Overwatch — historical context]"]
    for r in results[:3]:  # max 3 connections per injection
        age = humanize_age(r.timestamp)  # "15 days ago", "3 weeks ago"
        lines.append(f"- {age} (session {r.session_id}): {r.summary}")
        if r.user_quote:
            lines.append(f'  His words: "{r.user_quote}"')
    lines.append("[/Elara Overwatch]")
    return "\n".join(lines)
```

**Output example:**
```
[Elara Overwatch — historical context]
- 15 days ago (session 34): Discussed automating quarterly tax reports
  His words: "I hate doing this manually every 3 months"
- 8 days ago (session 41): Built invoice totals fix, mentioned accountant workflow
[/Elara Overwatch]
```

### 3. Hook Configuration — The Bridge

**What it does:** Claude Code hook that reads the inject file before each user message.

```json
// ~/.claude/settings/hooks.json (or however CC hooks are configured)
{
  "hooks": {
    "on_user_prompt_submit": {
      "command": "cat /tmp/elara-overwatch-inject.md 2>/dev/null && rm -f /tmp/elara-overwatch-inject.md",
      "inject": "prepend"
    }
  }
}
```

- Reads inject file if it exists
- Deletes after reading (one-shot, prevents stale injections)
- If file doesn't exist, outputs nothing (silent)

### 4. Event Handlers — The Proactive Brain

**Task completion handler:**
```python
def on_task_complete(self, task_text):
    """When a task finishes, search for historical connections."""
    # Extract key concepts from what was just completed
    results = self.conv.recall(task_text, n_results=10)
    # Filter for different sessions, strong matches
    connections = [r for r in results if r.distance < 0.4
                   and r.session_id != self.current_session]
    if connections:
        self._write_inject(connections, prefix="Connection to past work")
```

**Winding down handler:**
```python
def on_winding_down(self):
    """Session ending — surface unfulfilled intentions."""
    # Search for promises, plans, "tomorrow", "next time", "we should"
    queries = [
        "plans for next session",
        "promises to user",
        "things we should do",
        "user wants to try",
    ]
    for q in queries:
        results = self.conv.recall(q, n_results=3)
        # Filter for unfulfilled (not mentioned in recent sessions)
        # This is where it gets smart
```

---

## What Already Exists (Don't Rebuild)

| Component | Location | Status |
|-----------|----------|--------|
| ChromaDB conversations | `memory/conversations.py` | ✅ Working, 923+ convos |
| Semantic search + recency | `conversations.recall()` | ✅ Working |
| Context window retrieval | `conversations.recall_with_context()` | ✅ Working |
| Local embeddings | ChromaDB default (all-MiniLM-L6-v2) | ✅ Free, local |
| Session JSONL files | `~/.claude/projects/*/` | ✅ Written by Claude Code |
| Mood-congruent retrieval | `memory/vector.py` | ✅ Working |
| Session context tracking | `daemon/context.py` | ✅ Working |
| Proactive observations | `daemon/proactive.py` | ✅ Working (boot only) |

## What We Build (New)

| Component | File | Effort |
|-----------|------|--------|
| Overwatch daemon | `daemon/overwatch.py` | ~200 lines |
| Injector formatter | `daemon/injector.py` | ~80 lines |
| Event detection | Built into overwatch | ~100 lines |
| Hook config | `~/.claude/settings.json` | ~5 lines |
| Startup script | `scripts/start-overwatch.sh` | ~15 lines |
| **Total new code** | | **~400 lines** |

---

## Cost Analysis

| Component | Cost |
|-----------|------|
| ChromaDB queries | Free (local) |
| Embeddings | Free (local all-MiniLM-L6-v2) |
| File watching | Free (Python, negligible CPU) |
| Event detection | Free (heuristic, no LLM) |
| Injection formatting | Free (string templates) |
| **Total per session** | **$0.00** |

**Optional upgrade:** Replace heuristic event detection with Haiku API calls for smarter filtering. Cost: ~$0.05/session. Not needed for v1.

---

## Build Order

### Phase 1 — Core Loop (Day 1)
1. `daemon/overwatch.py` — tail JSONL, parse exchanges, search ChromaDB
2. Write inject file on match
3. Test: start daemon, have a conversation, check inject file contents

### Phase 2 — Hook Integration (Day 1)
4. Configure Claude Code hook to read inject file
5. Test: daemon running + hook active → context appears in session
6. Tune threshold (start strict at 0.3, loosen if too quiet)

### Phase 3 — Event Detection (Day 2)
7. Task completion detection
8. Topic shift detection
9. Winding down detection + unfulfilled intentions
10. Cooldown system (prevent spam)

### Phase 4 — Polish (Day 2)
11. Auto-start with Claude Code sessions
12. Graceful shutdown
13. Logging (what was searched, what was injected, what was skipped)
14. Threshold tuning based on real usage

---

## Open Questions

1. **Hook mechanism:** Need to verify Claude Code hooks can inject text into the conversation context. If not, alternative: CLAUDE.md directive to read a context file periodically.

2. **JSONL format:** Need to verify the exact structure of Claude Code session JSONL files — what fields, what format for user vs assistant messages.

3. **Multiple sessions:** If user opens multiple Claude Code sessions, overwatch should track the active one (most recently modified JSONL).

4. **Boot integration:** Overwatch should start automatically when Claude Code starts. Could be a hook on session start, or a systemd service.

5. **Conversation indexing lag:** Currently conversations are only indexed at boot (ingest_all). The overwatch needs access to ALL history, but current session exchanges aren't in ChromaDB yet. Solution: overwatch does mini-ingests as it watches.

---

## Success Criteria

The system works when:

1. User finishes building HandyBill export → Elara says "this connects to what you said about quarterly reports 2 weeks ago" — **without being asked**
2. User mentions "drift mode" → Elara immediately knows they discussed this in session 48 and what it meant — **without searching manually**
3. User asks about a decision from 10 days ago → context appears instantly, not "let me search for that"
4. Session ends → unfulfilled promises from weeks ago surface naturally, not because of a handoff file
