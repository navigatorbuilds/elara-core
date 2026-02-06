# Elara Core — Full Architecture Review

**Date:** 2026-02-06
**Purpose:** External review document for Kimi (or any reviewer)
**Context:** After major refactoring — server.py split, corrections v2, state.py split, dream.py split

---

## 1. What Is Elara?

A persistent emotional/memory framework for Claude Code (MCP server). Gives Claude continuity across sessions through:

- **Semantic memory** (ChromaDB) — facts, preferences, knowledge
- **Episodic memory** — session recordings with milestones & decisions
- **Conversation memory** — searchable past conversation history
- **Emotional state** — mood, imprints, temperament that decay over time
- **Dream mode** — weekly/monthly pattern discovery and self-reflection
- **Corrections** — never-decaying mistake tracking with contextual surfacing

**10,889 lines of Python** across 34 source files + re-export layers.

---

## 2. Directory Structure

```
elara-core/
├── core/elara.py              275 lines  Main orchestrator (wake/sleep/recall)
│
├── daemon/                               Persistent state & analysis
│   ├── state.py               45 lines   Re-export layer
│   ├── state_core.py          192 lines  Constants, load/save, decay
│   ├── mood.py                341 lines  Mood get/set/adjust, imprints, descriptions
│   ├── emotions.py            403 lines  Circumplex emotion model (38 emotions)
│   ├── sessions.py            255 lines  Episode/session lifecycle
│   ├── temperament.py         145 lines  Emotional growth system
│   ├── presence.py            167 lines  Session tracking
│   ├── goals.py               158 lines  Goal tracking
│   ├── corrections.py         381 lines  Corrections v2 (ChromaDB + conditions)
│   ├── context.py             189 lines  Quick session context
│   ├── self_awareness.py      639 lines  reflect(), pulse(), blind_spots()
│   ├── proactive.py           420 lines  Boot/mid-session observations
│   ├── dream.py               26 lines   Re-export layer
│   ├── dream_core.py          239 lines  Dream utilities, status, data gathering
│   ├── dream_weekly.py        259 lines  Weekly pattern analysis
│   ├── dream_monthly.py       331 lines  Monthly narrative threading
│   └── dream_emotional.py     627 lines  Temperament growth, tone calibration
│
├── memory/                               Semantic search (ChromaDB)
│   ├── vector.py              467 lines  Semantic memory + mood-congruent retrieval
│   ├── episodic.py            689 lines  Autobiographical memory (episodes)
│   └── conversations.py       858 lines  Conversation search + auto-ingestion
│
├── elara_mcp/                            Claude Code interface (47 MCP tools)
│   ├── _app.py                11 lines   FastMCP instance
│   ├── server.py              29 lines   Tool registry (imports all tool modules)
│   └── tools/
│       ├── memory.py          258 lines  8 tools
│       ├── mood.py            288 lines  10 tools
│       ├── episodes.py        416 lines  13 tools
│       ├── goals.py           218 lines  7 tools
│       ├── awareness.py       269 lines  7 tools
│       └── dreams.py          237 lines  3 tools (but compound)
│
├── interface/                            User-facing
│   ├── web.py                 650 lines  Flask dashboard
│   ├── storage.py             109 lines  Notes/messages
│   └── notify.py              95 lines   Desktop notifications
│
├── senses/                               Environment awareness
│   ├── system.py              103 lines  CPU/memory/disk
│   ├── activity.py            186 lines  Terminal activity
│   └── ambient.py             122 lines  Time/weather
│
├── watcher/                              Background worker
│   ├── worker.py              262 lines  Main loop
│   ├── worker_ctl.py          106 lines  Control interface
│   └── auto_worker.py         106 lines  Auto-start
│
├── voice/tts.py               155 lines  Piper TTS integration
└── hooks/boot.py              137 lines  Session bootstrap
```

---

## 3. Layer Architecture

```
┌──────────────────────────────────────────┐
│          MCP Tools (47 tools)            │  Claude Code calls these
│     elara_mcp/tools/{domain}.py          │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│         Core Orchestrator                │  core/elara.py
│     wake() → process() → sleep()         │
└────────────────┬─────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
┌─────────┐ ┌─────────┐ ┌────────────┐
│ Daemon  │ │ Memory  │ │ Interface  │
│ State   │ │ System  │ │ & Senses   │
│         │ │         │ │            │
│ mood    │ │ vector  │ │ web        │
│ sessions│ │ episodic│ │ notify     │
│ temper. │ │ convos  │ │ system     │
│ dreams  │ │         │ │ activity   │
│ goals   │ │ (Chroma │ │ ambient    │
│ correct.│ │  DB)    │ │            │
│ aware.  │ │         │ │            │
└─────────┘ └─────────┘ └────────────┘
```

---

## 4. Storage Map

All under `~/.claude/`:

### JSON State Files (read/write atomically)
| File | Purpose |
|------|---------|
| `elara-state.json` | Current mood, temperament, imprints, residue, session |
| `elara-goals.json` | Goal tracking |
| `elara-presence.json` | Session history, total time together |
| `elara-corrections.json` | Never-decaying mistakes (source of truth) |
| `elara-context.json` | Quick session context |
| `elara-intention.json` | Growth intention |
| `elara-pulse.json` | Relationship health snapshot |
| `elara-blind-spots.json` | What am I missing |
| `elara-proactive-session.json` | Observation cooldowns |

### JSONL Archives (append-only)
| File | Purpose |
|------|---------|
| `elara-mood-journal.jsonl` | Every mood change with timestamp |
| `elara-imprint-archive.jsonl` | Imprints that decayed away |
| `elara-temperament-log.jsonl` | Every temperament adjustment |

### ChromaDB Collections (4 total)
| Collection | Path | Content |
|------------|------|---------|
| `elara_memories` | `elara-memory-db/` | Semantic memories (facts, moments, feelings) |
| `elara_milestones` | `elara-episodes-db/` | Milestone events from episodes |
| `elara_conversations_v2` | `elara-conversations-db/` | User/assistant exchange pairs |
| `elara_corrections` | `elara-corrections-db/` | Mistake patterns for contextual surfacing |

### Episodic Storage
```
elara-episodes/
├── index.json                    Episode metadata index
└── YYYY-MM/
    └── YYYY-MM-DD-HHMM.json     Individual episode records
```

### Dream Reports
```
elara-dreams/
├── status.json                   Last run timestamps
├── weekly/latest.json + dated    Weekly analysis
├── monthly/latest.json + dated   Monthly analysis
├── threads/latest.json           Narrative arcs
└── emotional/latest.json         Temperament calibration
```

---

## 5. Dependency Graph

### Foundation (no daemon deps)
- `daemon/emotions.py` — 38-emotion circumplex model, pure math
- `daemon/presence.py` — session tracking, standalone
- `daemon/goals.py` — goal CRUD, standalone
- `daemon/context.py` — context save/load, standalone

### State Layer
```
daemon/state_core.py ← daemon/emotions (get_primary_emotion)
daemon/mood.py ← daemon/state_core + daemon/emotions
daemon/temperament.py ← daemon/state_core
daemon/sessions.py ← daemon/state_core + daemon/mood
daemon/state.py (re-export) ← all above
```

### Memory Layer (independent, optional daemon imports)
```
memory/vector.py ← optional daemon/state (mood-congruent retrieval)
memory/episodic.py ← optional daemon/state (mood tagging)
memory/conversations.py ← standalone
```

### Analysis Layer (lazy imports to avoid cycles)
```
daemon/corrections.py ← standalone + optional chromadb
daemon/self_awareness.py ← lazy: state, goals, corrections, episodic, dream
daemon/proactive.py ← lazy: presence, state, goals, episodic
```

### Dream Layer (lazy imports)
```
daemon/dream_core.py ← lazy: goals, corrections, state, episodic, vector
daemon/dream_weekly.py ← dream_core + lazy: self_awareness, dream_emotional
daemon/dream_monthly.py ← dream_core, dream_weekly + lazy: dream_emotional
daemon/dream_emotional.py ← dream_core + lazy: mood, temperament, self_awareness
daemon/dream.py (re-export) ← all above
```

### MCP Tools (leaf nodes, consume everything)
```
elara_mcp/tools/* ← daemon/*, memory/*
```

**Circular dependencies: NONE** — all potential cycles broken by lazy imports inside functions.

---

## 6. Key Design Patterns

### Re-Export Layers
`state.py` and `dream.py` are thin re-export files. External code imports from them, internal code imports from submodules directly. Refactoring internals never breaks external imports.

### Lazy Imports
Dream, awareness, and proactive modules use `from X import Y` inside function bodies to avoid import-time circular dependencies.

### Mood Decay on Load
Every `get_mood()` call applies exponential time-decay toward temperament baseline:
```python
decay_factor = 1 - exp(-DECAY_RATE * hours_elapsed)
new_val = current + (baseline - current) * decay_factor
```
Imprints below 0.1 strength get archived to JSONL.

### Mood-Congruent Memory
Semantic recall blends similarity score (70%) with emotional resonance (30%). Current mood affects what memories surface.

### Temperament Growth
Emotional dreams compute micro-adjustments (max ±0.03/week per dimension) based on drift session mood, imprint accumulation, and us.md entries. Factory decay (15%/week) prevents runaway drift.

### Corrections v2
Two-track system:
- **Tendencies** (always boot-loaded): behavioral patterns
- **Technical** (contextually searched): task-specific mistakes
- Each has `fails_when`/`fine_when` conditions to prevent overgeneralization
- ChromaDB semantic search surfaces relevant corrections by task context
- Activation tracking (last_activated, times_surfaced, times_dismissed)
- Dormant detection feeds into blind_spots()

---

## 7. Session Lifecycle

```
BOOT (hooks/boot.py)
├── get_elara() → singleton init
├── Elara.wake() → presence.ping(), start_session()
├── corrections.ensure_index() → sync to ChromaDB
├── conversations.ingest_all() → index new session files
└── Return context (mood, absence, memory count)

DURING SESSION
├── MCP tools called by Claude Code
├── adjust_mood() on each interaction
├── Milestones/decisions recorded to current episode
├── check_corrections() for relevant past mistakes
└── observe_now() at natural break points

END (bye trigger)
├── end_episode() → finalize, record mood trajectory
├── end_session() → save state, update presence
├── Save memory file
└── Optional: reflect(), pulse()
```

---

## 8. JSON Schemas

### State (`elara-state.json`)
```json
{
  "mood": { "valence": -1..1, "energy": 0..1, "openness": 0..1 },
  "temperament": { "valence": 0.55, "energy": 0.5, "openness": 0.65 },
  "imprints": [{ "feeling": "str", "strength": 0..1, "created": "ISO" }],
  "residue": [{ "time": "ISO", "reason": "str", "type": "str" }],
  "allostatic_load": 0..1,
  "flags": { "had_deep_conversation": bool, "late_night_session": bool, ... },
  "current_session": { "id": "str", "type": "work|drift|mixed", "projects": [] },
  "last_update": "ISO",
  "consolidation": { "sleep_debt": 0..1 }
}
```

### Episode
```json
{
  "id": "2026-02-05-1402",
  "type": "work|drift|mixed",
  "started": "ISO", "ended": "ISO",
  "projects": ["handybill"],
  "mood_start": {}, "mood_end": {}, "mood_delta": -1..1,
  "milestones": [{ "event": "str", "type": "completion|insight|error", "importance": 0..1 }],
  "decisions": [{ "what": "str", "why": "str", "confidence": "low|medium|high" }],
  "summary": "str"
}
```

### Correction (v2)
```json
{
  "id": 1,
  "mistake": "str", "correction": "str", "context": "str",
  "correction_type": "tendency|technical",
  "fails_when": "condition where this applies",
  "fine_when": "condition where this doesn't apply",
  "date": "ISO",
  "last_activated": "ISO|null",
  "times_surfaced": 0, "times_dismissed": 0
}
```

---

## 9. 47 MCP Tools (Full List)

### Memory (8)
`elara_remember`, `elara_recall`, `elara_recall_conversation`, `elara_recall_conversation_context`, `elara_episode_conversations`, `elara_ingest_conversations`, `elara_conversation_stats`, `elara_search_milestones`

### Mood & Emotions (10)
`elara_mood_get`, `elara_mood_update`, `elara_emotions`, `elara_session_arc`, `elara_imprint`, `elara_describe_self`, `elara_residue`, `elara_mode`, `elara_status`, `elara_temperament`

### Episodes & Context (13)
`elara_episode_start`, `elara_episode_end`, `elara_episode_current`, `elara_milestone`, `elara_decision`, `elara_recall_episodes`, `elara_episode_stats`, `elara_project_history`, `elara_context`, `elara_context_get`, `elara_context_toggle`

### Goals & Corrections (7)
`elara_goal_add`, `elara_goal_update`, `elara_goal_list`, `elara_goal_boot`, `elara_correction_add`, `elara_correction_list`, `elara_correction_boot`, `elara_check_corrections`

### Awareness (7)
`elara_reflect`, `elara_pulse`, `elara_blind_spots`, `elara_intention`, `elara_awareness_boot`, `elara_observe_boot`, `elara_observe_now`

### Dreams (3)
`elara_dream`, `elara_dream_status`, `elara_dream_read`

---

## 10. External Dependencies

| Package | Purpose |
|---------|---------|
| `chromadb` | Vector DB (4 collections) |
| `mcp[cli]` (FastMCP) | Claude Code integration |
| `flask` | Web dashboard |
| `psutil` | System monitoring |
| `pyyaml` | Config parsing |
| `python-dateutil` | Date utilities |

System: `git`, `notify-send`, `piper` (TTS), `fswatch`

---

## 11. Recent Changes (This Session)

| Change | Before | After |
|--------|--------|-------|
| `server.py` split | 1,715 lines | 29 lines + 6 tool modules |
| Corrections v2 | 86 lines, flat list | 381 lines, ChromaDB + conditions + activation tracking |
| `state.py` split | 1,077 lines | 5 modules (192 + 341 + 255 + 145 + 45 re-export) |
| `dream.py` split | 1,618 lines | 5 modules (239 + 259 + 331 + 627 + 26 re-export) |

---

## 12. Open Questions for Review

1. **self_awareness.py (639 lines)** — Largest remaining unsplit file. Contains reflect(), pulse(), blind_spots(), observations. Worth splitting?

2. **proactive.py (420 lines)** — Second largest. Multiple observation checkers. Same question.

3. **conversations.py (858 lines)** — Largest in memory/. Handles ingestion + search + context. Could split ingestion from query.

4. **ChromaDB coupling** — 4 collections, all with try-except fallback. But if ChromaDB goes down, corrections search, conversation search, and milestone search all degrade silently. Is silent degradation the right choice?

5. **State file contention** — `elara-state.json` is read-modify-written by multiple code paths (mood, sessions, temperament). No locking. Race condition risk if worker and MCP tools run simultaneously?

6. **Dream interdependencies** — weekly_dream() calls emotional_dream(), monthly_dream() calls monthly_emotional_dream(). If emotional dream fails, weekly/monthly still complete but with `{"emotional": {"error": "..."}}`. Is this the right error boundary?

7. **Correction overgeneralization** — v2 added `fails_when`/`fine_when` but existing corrections need manual population. Auto-extraction from context feasible?

8. **Memory decay rates** — Mood decays toward temperament. Imprints decay to archive. But semantic memories (ChromaDB) never decay. Should they?

---

*Generated for architectural review. Commit b8fb3cb.*
