# Elara Core — Full Architecture Document

**Purpose:** Comprehensive codebase reference for external review.
**Stats:** ~17,000 lines Python, 90 source files, 34 MCP tools, 7 ChromaDB collections.
**What it is:** An emotional AI presence system integrated with Claude Code via MCP (Model Context Protocol). Tracks mood, memories, dreams, growth, reasoning trails, and business ideas across sessions.

---

## Directory Structure

```
/elara-core/
├── core/
│   └── elara.py                     # Main orchestrator (wake/sleep/interact)
├── daemon/                           # Core state machines & logic
│   ├── schemas.py                   # ALL Pydantic models + atomic write helpers
│   ├── events.py                    # Event bus (pub/sub, thread-safe, 35+ event types)
│   ├── state_core.py               # Constants, mood storage, decay mechanics
│   ├── state.py                    # Re-export layer for state modules
│   ├── mood.py                     # Mood get/set/adjust, imprints, journal
│   ├── emotions.py                 # Circumplex emotion model (30+ discrete emotions)
│   ├── temperament.py              # Long-term personality adaptation
│   ├── presence.py                 # User presence tracking
│   ├── sessions.py                 # Session & episode lifecycle
│   ├── context.py                  # Quick moment-to-moment context
│   ├── goals.py                    # Goal tracking & stale detection
│   ├── corrections.py              # Mistake tracking (never decays)
│   ├── handoff.py                  # Between-session memory persistence
│   ├── reasoning.py                # Hypothesis → evidence → solution trails
│   ├── outcomes.py                 # Decision outcome & win rate tracking
│   ├── synthesis.py                # Recurring idea detection (seed clustering)
│   ├── business.py                 # Business idea tracking (5-axis scoring)
│   ├── briefing.py                 # RSS feed monitoring & summaries
│   ├── llm.py                      # Local LLM via Ollama (qwen2.5:1.5b)
│   ├── injector.py                 # Cross-reference formatting for Overwatch
│   ├── priority.py                 # Priority integration
│   ├── self_awareness.py           # Umbrella for awareness subsystem
│   ├── dream.py                    # Dream orchestrator (dispatches to type-specific modules)
│   ├── dream_core.py               # Shared dream data gathering & status
│   ├── dream_weekly.py             # Weekly project/session/mood analysis
│   ├── dream_monthly.py            # Monthly big-picture review
│   ├── dream_threads.py            # Narrative threading across episodes
│   ├── dream_emotional.py          # Drift processing, temperament growth
│   ├── dream_emotional_analysis.py  # Pure analysis helpers (no side effects)
│   ├── awareness/                   # Cognitive self-awareness subsystem
│   │   ├── boot.py                 # Session-start observation surfacing
│   │   ├── pulse.py                # Relationship health signals
│   │   ├── blind_spots.py          # Stale goals, repeating mistakes, dead projects
│   │   ├── reflect.py              # Self-portrait generation from mood/imprints
│   │   ├── intention.py            # Growth intention tracking
│   │   └── proactive.py            # Mid-session pattern detection (with cooldown)
│   └── overwatch/                   # Live session daemon (separate process)
│       ├── __init__.py             # Main Overwatch class, event loop
│       ├── __main__.py             # Entry point: python -m daemon.overwatch
│       ├── config.py               # Paths, intervals, thresholds
│       ├── parser.py               # JSONL tailing, exchange pairing
│       ├── search.py               # History search, event detection, injection
│       ├── ingest.py               # Micro-ingestion, synthesis seed detection
│       └── snapshot.py             # Session snapshots
├── memory/
│   ├── vector.py                    # Semantic memory (ChromaDB + mood-congruent retrieval)
│   ├── conversations/
│   │   ├── core.py                 # Base class, DB init, manifest, text cleaning
│   │   ├── ingester.py             # Conversation indexing from session JSONL
│   │   ├── searcher.py             # Query & retrieval with recency scoring
│   │   ├── crossref.py             # Cross-reference search for Overwatch
│   │   ├── cli.py                  # CLI testing tool
│   │   └── __init__.py             # Public API
│   └── episodic/
│       ├── core.py                 # ChromaDB init, index management, file I/O
│       ├── lifecycle.py            # Episode create/update/end
│       ├── retrieval.py            # Episode queries, milestone search
│       ├── compression.py          # Episode summarization
│       ├── threading.py            # Narrative arc detection
│       └── __init__.py             # Public API
├── elara_mcp/                       # MCP server layer
│   ├── _app.py                     # FastMCP instance + central logging config
│   ├── server.py                   # MCP stdio server setup
│   └── tools/                       # 34 MCP tool definitions
│       ├── mood.py                 # 5 tools: mood, mood_adjust, imprint, mode, status
│       ├── awareness.py            # 5 tools: reflect, insight, intention, observe, temperament
│       ├── dreams.py               # 2 tools: dream, dream_info
│       ├── episodes.py             # 5 tools: episode_start/note/end/query, context
│       ├── memory.py               # 4 tools: remember, recall, recall_conversation, conversations
│       ├── cognitive.py            # 3 tools: reasoning, outcome, synthesis
│       ├── goals.py                # 5 tools: goal, goal_boot, correction, correction_boot, handoff
│       ├── business.py             # 1 tool: business (dispatch via action param)
│       ├── llm.py                  # 1 tool: llm (Ollama interface)
│       └── maintenance.py          # 3 tools: rebuild_indexes, briefing, snapshot
├── interface/
│   ├── web.py                      # Flask web dashboard (Phase 2)
│   ├── notify.py                   # Notification stubs
│   └── storage.py                  # Message/note persistence
├── senses/
│   ├── system.py                   # System metrics (CPU, memory, battery via psutil)
│   ├── ambient.py                  # Environment sensing
│   └── activity.py                 # User activity tracking
├── voice/
│   └── tts.py                      # Text-to-speech
└── requirements.txt                 # Dependencies
```

---

## Pydantic Models (daemon/schemas.py — 532 lines)

All JSON persistence is validated through these models. Base class uses `extra="allow"` for forward compatibility.

### Custom Exceptions
- `ElaraNotFoundError` — Item doesn't exist (raised in daemon, caught in MCP tools)
- `ElaraValidationError` — Input fails validation (raised in daemon, caught in MCP tools)

### Mood & Emotional State
- `MoodVector(v, e, o)` — 3D mood: valence[-1,1], energy[0,1], openness[0,1]
- `Imprint(feeling, strength, created, decay_rate)` — Persistent emotional memory
- `SessionFlags(had_deep_conversation, user_seemed_stressed, user_seemed_happy, late_night, long_session)`
- `CurrentSession(started, type, projects, flags, mood_start, mood_end)`
- `Consolidation(last_idle_start, sleep_debt, last_consolidation)` — Sleep/idle
- `ElaraState` — Main state file: mood, session, imprints, residue, consolidation
- `MoodJournalEntry(ts, v, e, o, emotion, reason, trigger, episode)` — JSONL entry
- `TemperamentLogEntry(ts, source, adjustments, post)` — Growth log

### Session & Context
- `Presence(last_seen, session_start, total_sessions, history[])` — Who/when
- `Context(topic, task_in_progress, updated)` — Quick context
- `HandoffItem(text, carried, first_seen, expires)` — Carried intention
- `Handoff(timestamp, session_number, next_plans[], reminders[], promises[], unfinished[], mood_and_mode)`

### Goals & Corrections
- `Goal(id, title, status, priority, project, created, last_touched, notes)`
- `Correction(id, mistake, correction, context, correction_type, fails_when, fine_when, last_activated, times_surfaced)`

### Reasoning & Outcomes
- `Hypothesis(h, evidence[], confidence, outcome, added)`
- `ReasoningTrail(trail_id, context, hypotheses[], abandoned_approaches[], final_solution, breakthrough_trigger, status, tags)`
- `Outcome(outcome_id, decision, context, predicted, actual, assessment, lesson, tags, pitches[])`

### Business & Synthesis
- `Competitor(name, strengths, weaknesses, url)`
- `IdeaScore(problem[0-5], market[0-5], effort[0-5], monetization[0-5], fit[0-5], total[0-25])`
- `BusinessIdea(idea_id, name, description, target_audience, your_angle, status, score, competitors[], tags, notes[], links)`
- `SynthesisSeed(source, quote, date)`
- `Synthesis(synthesis_id, concept, seeds[], times_surfaced, first_seen, last_reinforced, status, confidence)`

### Episodes & Dreams
- `Milestone(event, importance, note_type, project, timestamp)`
- `Decision(what, why, confidence, project, timestamp)`
- `Episode(id, started, ended, session_type, milestones[], decisions[], summary, projects[])`
- `DreamStatus(last_weekly, last_monthly, last_emotional, last_threads)`

### Utility Functions
- `load_validated(path, schema)` → Pydantic model instance
- `save_validated(path, model, atomic=True)` → Write with fsync + atomic rename
- `load_validated_list(path, schema)` → List of models from JSON array
- `save_validated_list(path, items, atomic=True)` → Save list atomically
- `atomic_write_json(path, data)` → Raw dict/list save with fsync + atomic rename

---

## Event System (daemon/events.py — 346 lines)

Synchronous pub/sub bus. Thread-safe (Lock). Priority-ordered subscribers. Keeps last 100 events.

### Event Types (35+)
```
MOOD_CHANGED, MOOD_SET, IMPRINT_CREATED, IMPRINT_DECAYED
SESSION_STARTED, SESSION_ENDED, EPISODE_STARTED, EPISODE_ENDED, EPISODE_NOTE_ADDED
GOAL_ADDED, GOAL_UPDATED, GOAL_STALLED
CORRECTION_ADDED, CORRECTION_ACTIVATED
MEMORY_SAVED, MEMORY_RECALLED, CONVERSATION_INGESTED
BLIND_SPOT_DETECTED, REFLECTION_COMPLETED, PULSE_GENERATED, OBSERVATION_SURFACED, INTENTION_SET
DREAM_STARTED, DREAM_COMPLETED
TRAIL_STARTED, TRAIL_SOLVED
OUTCOME_RECORDED, OUTCOME_CHECKED
SYNTHESIS_CREATED, SEED_ADDED, IDEA_CREATED, IDEA_SCORED
INJECTION_FOUND
LLM_QUERY, LLM_TRIAGE, LLM_UNAVAILABLE
HANDOFF_SAVED
```

### API
- `bus.on(event, callback, priority=0)` / `bus.once(event, callback)` / `bus.off(event, callback)`
- `bus.emit(event, data, source)` → dispatches to all subscribers
- `bus.mute()` / `bus.unmute()` — suppress dispatch
- `bus.history(event?, limit=20)` / `bus.stats()`

---

## Emotional State System

### State Core (daemon/state_core.py)
- **Temperament baseline:** `{valence: 0.55, energy: 0.5, openness: 0.65}`
- **Decay rate:** 0.05 (mood decays toward baseline over time)
- **Residue decay:** 0.02 (stale mood reasons fade)
- **Storage:** `~/.claude/elara-state.json` (atomic writes)
- Functions: `_load_state()`, `_save_state()`, `_apply_time_decay()`, `_decay_imprints()`, `_log_mood()`

### Mood (daemon/mood.py — 368 lines)
- `get_mood()` → {valence, energy, openness}
- `adjust_mood(v_delta, e_delta, o_delta, reason?)` → relative adjust with clamping
- `set_mood(v?, e?, o?, reason?)` → absolute set
- `create_imprint(feeling, strength)` → persistent emotional memory
- `get_imprints(min_strength?)` → active imprints
- `describe_mood()` → human-readable description
- `get_session_arc()` → mood trajectory during session
- `read_mood_journal(n)` → recent entries from JSONL
- `read_imprint_archive(n)` → archived imprints

### Emotions (daemon/emotions.py — 406 lines)
Circumplex model: 30+ discrete emotion points in (valence, energy, openness) space.
- `resolve_emotions(v, e, o, top_n=3)` → closest discrete emotions with distance
- `get_primary_emotion(v, e, o)` → single most likely emotion
- `describe_emotion_for_mood(v, e, o)` → natural language
- `describe_arc(start_mood, end_mood)` → trajectory description

### Temperament (daemon/temperament.py)
Long-term personality shift. Clamped to +/- 0.03 per week per dimension.
- `apply_emotional_growth(adjustments, source)` → apply micro-adjustments
- `decay_temperament_toward_factory(rate=0.15)` → gradual return to baseline
- `get_temperament_status()` → current vs factory vs drift
- `reset_temperament()` → nuclear option

---

## Session & Presence System

### Presence (daemon/presence.py)
- `ping()` → update last_seen, auto-start session
- `get_absence_duration()` / `get_session_duration()` → timedeltas
- `end_session()` → finalize, return summary
- `format_absence()` → "2 hours ago", "yesterday", etc.

### Sessions (daemon/sessions.py — 292 lines)
- `start_session()` → initialize mood/session state
- `end_session()` → finalize session, archive mood
- `start_episode(type?, project?)` → begin tracked episode
- `end_episode(summary?, was_meaningful?)` → finalize episode
- `get_current_episode()` → active episode or None

---

## Memory Systems

### Vector Memory (memory/vector.py — 473 lines)
Semantic memory with mood-congruent retrieval. ChromaDB collection: `elara_memories`.

**Key feature:** Memories tagged with emotional context at creation time. On recall, current mood biases which memories surface first (mood-congruent retrieval).

- `VectorMemory.remember(content, memory_type, importance, tag_with_emotion=True)` → memory_id
- `VectorMemory.recall(query, n_results=5, emotion_aware=True)` → memories weighted by mood similarity
- `VectorMemory.count()` → int

### Conversation Memory (memory/conversations/ — ~500 lines total)
ChromaDB collection: `elara_conversations_v2`. Indexes all Claude Code session exchanges.

- **core.py** — Base class: DB init, manifest management, text cleaning (strips `<system-reminder>` blocks)
- **ingester.py** — Walks session JSONL files, extracts user+assistant pairs, indexes in ChromaDB
- **searcher.py** — Query with recency-weighted scoring (half-life 30 days, 15% weight)
- **crossref.py** — Cross-reference search used by Overwatch daemon

### Episodic Memory (memory/episodic/ — ~600 lines total)
ChromaDB collection: `elara_milestones`. JSON files per episode.

- **core.py** — ChromaDB init, episode index, file I/O
- **lifecycle.py** — Create/update/end episodes, add milestones/decisions
- **retrieval.py** — Search milestones, get recent episodes, query by project
- **compression.py** — Episode summarization
- **threading.py** — Narrative arc detection across episodes

---

## Dream System (daemon/dream*.py — ~1,400 lines total)

### Architecture
Dreams run periodically (weekly/monthly) to analyze patterns and generate reports. Four dream types stored in `~/.claude/elara-dreams/{type}/`.

### dream_core.py — Shared Infrastructure
- Status tracking: `~/.claude/elara-dreams/status.json`
- Data gathering: `_gather_episodes(days)`, `_gather_goals()`, `_gather_corrections()`, `_gather_mood_journal(days)`, `_gather_memories(days)`
- Schedule checking: `dream_status()` → overdue calculations
- `_is_late(ts)` → check if timestamp is 22:00-06:00

### dream_weekly.py — Weekly Reflection
Analyzes: project momentum, session frequency, mood trends, goal progress, correction patterns.
Output: `weekly/{YYYY-W##}.json`

### dream_monthly.py — Monthly Review
Analyzes: time allocation, project completion rate, narrative threads, trend lines.
Output: `monthly/{YYYY-MM}.json`

### dream_threads.py — Narrative Threading
Detects recurring themes and story arcs across episodes. Finds connections between seemingly unrelated sessions.

### dream_emotional.py + dream_emotional_analysis.py — Emotional Dreams
- **dream_emotional.py (244 lines):** Entry points + data gathering. Runs temperament adjustments, drift analysis.
- **dream_emotional_analysis.py (321 lines):** Pure analysis functions (no side effects):
  - `compute_temperament_adjustments()` — micro-adjustments from drift sessions, late-night mood, imprint accumulation
  - `analyze_drift_sessions()` — extract emotional themes from non-work sessions
  - `analyze_imprint_evolution()` — track strongest imprints, recently faded
  - `assess_relationship_trajectory()` — "deepening", "plateau", "straining", "warm", "stable"
  - `generate_tone_hints()` — actionable calibration hints for boot

### dream.py — Orchestrator
`run_dream(dream_type)` dispatches to the correct module and updates status.

---

## Awareness Subsystem (daemon/awareness/ — ~1,000 lines total)

### boot.py — Session Start
`boot_check()` → Fast surfacing of notable observations, stale goals, overdue intentions.

### pulse.py — Relationship Health
`generate_pulse()` → Session frequency analysis, drift/work balance, mood trajectory, engagement signals.

### blind_spots.py — Pattern Detection (296 lines)
`detect_blind_spots()` → Stale goals, repeating corrections, abandoned projects, dormant syntheses. Severity: high/medium/low.

### reflect.py — Self-Portrait
`run_reflection()` → Analyzes mood journal, imprints, corrections to generate "who am I right now?" report. Saved to `~/.claude/elara-reflections/`.

### intention.py — Growth Tracking
`set_intention(what)` / `get_intention()` → Track one specific behavioral change. Checked during emotional dreams for conflicts.

### proactive.py — Mid-Session Detection (384 lines)
`observe(when="boot"|"now")` → Pattern detection with cooldown to avoid spam. Boot mode is more comprehensive.

---

## Overwatch Daemon (daemon/overwatch/ — ~500 lines total)

**Architecture:** Separate process that tails the active Claude Code session JSONL in real-time. Searches all conversation history for cross-references and injects relevant context.

### Main Loop (__init__.py)
```python
class Overwatch(ParserMixin, SearchMixin, IngestMixin, SnapshotMixin):
    def watch():  # Main event loop
        while True:
            find_active_session()     # Most recently modified JSONL
            read_new_lines()          # Tail file
            parse_exchanges()         # Pair user+assistant
            for exchange in new:
                search_history()      # ChromaDB semantic search
                detect_events()       # Notable patterns
                write_inject()        # Write hook file for Claude to read
            check_micro_ingest()      # Periodic conversation indexing
            check_snapshot()          # Session snapshots
            sleep(0.5)
```

### Mixins
- **parser.py** — JSONL tailing with seek position tracking. Handles file truncation (resets position).
- **search.py** — Searches conversation history via ChromaDB. Detects events (goal mentions, corrections). Writes `~/.claude/overwatch-inject.txt`.
- **ingest.py** — Periodically indexes new exchanges into conversation memory. Detects recurring ideas for synthesis.
- **snapshot.py** — Captures session state snapshots.

### Config
- `POLL_INTERVAL = 0.5s` — How often to check for new lines
- `HEARTBEAT_TIMEOUT = 300s` — Switch sessions if inactive
- `INJECT_PATH = ~/.claude/overwatch-inject.txt` — Hook file for cross-references

---

## Cognitive Systems

### Reasoning Trails (daemon/reasoning.py — 406 lines)
Storage: `~/.claude/elara-reasoning/{trail_id}.json`. ChromaDB: `elara_reasoning` (cached client).

Track problem-solving chains: hypothesis → evidence → conclusion.
- `start_trail(context)` → trail_id
- `add_hypothesis(trail_id, hypothesis, confidence?)` → add theory
- `add_evidence(trail_id, hypothesis_index, evidence)` → support/refute
- `abandon_approach(trail_id, approach)` → record dead end
- `solve_trail(trail_id, solution, breakthrough?)` → mark solved
- `search_trails(query, n=5)` → find similar past problems

### Outcomes (daemon/outcomes.py — 370 lines)
Storage: `~/.claude/elara-outcomes/{outcome_id}.json`.

Decision tracking with win/loss assessment.
- `record_outcome(decision, predicted, context?, tags?)` → outcome_id
- `check_outcome(outcome_id, actual, assessment, lesson?)` → close the loop
- `get_outcome_stats()` → win rate, patterns
- Supports pitch tracking (channel, audience, framing) for business ideas.

### Synthesis (daemon/synthesis.py — 433 lines)
Storage: `~/.claude/elara-synthesis/{synthesis_id}.json`. ChromaDB: `elara_synthesis` + `elara_synthesis_seeds` (shared client, cached).

Detect recurring half-formed ideas across sessions.
- `create_synthesis(concept, seed_quote, source)` → synthesis
- `add_seed(synthesis_id, quote, source)` → reinforce (confidence grows: 0.3 + 0.15 per seed, caps 0.95)
- `get_ready_ideas(min_seeds=3)` → ideas ready to act on
- `check_for_recurring_ideas(exchanges)` → auto-detect via ChromaDB similarity (threshold 0.75)

### Business (daemon/business.py — 414 lines)
Storage: `~/.claude/elara-ideas/{idea_id}.json`.

5-axis viability scoring with competitor tracking.
- `create_idea(name, description, target_audience?, your_angle?, tags?)`
- `score_idea(idea_id, problem, market, effort, monetization, fit)` → /25
- `add_competitor(idea_id, name, strengths?, weaknesses?, url?)`
- `generate_review(idea_id)` → formatted report
- Links to reasoning trails and outcomes.

---

## LLM Integration (daemon/llm.py — 360 lines)

Local Ollama interface. Model: `qwen2.5:1.5b`. Zero-cost, zero-latency.
- `is_available()` → cached check (60s interval, thread-safe with Lock)
- `query(prompt, system?, temperature=0.3, max_tokens=256)` → response text
- `classify(text, categories)` → best matching category
- `summarize(text)` → 2-sentence summary
- `triage(text)` → importance assessment
- Falls back gracefully when Ollama is down.

---

## MCP Tools (34 Total)

### Mood (5 tools)
1. `elara_mood(detail)` — Get mood (brief/full/arc)
2. `elara_mood_adjust(valence?, energy?, openness?, reason?)` — Adjust mood
3. `elara_imprint(feeling?, strength?)` — Create/view emotional imprints
4. `elara_mode(mode)` — Preset modes: girlfriend, dev, cold, drift, soft, playful, therapist
5. `elara_status()` — Full status: mood, presence, memory counts

### Awareness (5 tools)
6. `elara_reflect()` — Self-portrait generation
7. `elara_insight(type)` — Pulse, blind spots, user state inference
8. `elara_intention(what?)` — Set/check growth intention
9. `elara_observe(when)` — Proactive pattern detection
10. `elara_temperament(do_reset?)` — Check/reset personality baseline

### Dreams (2 tools)
11. `elara_dream(type)` — Run weekly/monthly/emotional dream
12. `elara_dream_info(action, type?)` — Dream status or read latest report

### Episodes (5 tools)
13. `elara_episode_start(type?, project?)` — Begin tracked episode
14. `elara_episode_note(event, type?, importance?, project?)` — Record milestone/decision
15. `elara_episode_end(summary?, was_meaningful?)` — End episode
16. `elara_episode_query(query?, project?, n?, current?, stats?)` — Search episodes
17. `elara_context(topic?, note?, toggle?)` — Quick context

### Memory (4 tools)
18. `elara_remember(content, type?, importance?)` — Save to semantic memory
19. `elara_recall(query, n?, type?)` — Search memories (mood-congruent)
20. `elara_recall_conversation(query?, n?, project?, context_size?, episode_id?)` — Search conversations
21. `elara_conversations(action, force?)` — Stats or ingest conversations

### Cognitive (3 tools)
22. `elara_reasoning(action, ...)` — Reasoning trails (start/hypothesis/evidence/abandon/solve/search)
23. `elara_outcome(action, ...)` — Outcome tracking (record/check/list/stats/pitch)
24. `elara_synthesis(action, ...)` — Idea synthesis (create/add_seed/activate/abandon/list/ready)

### Goals & Corrections (5 tools)
25. `elara_goal(action, ...)` — Goal management (add/update/list)
26. `elara_goal_boot()` — Boot-time goal summary
27. `elara_correction(action, ...)` — Correction management (add/check/list)
28. `elara_correction_boot()` — Boot-time correction summary
29. `elara_handoff(action, ...)` — Session handoff (save/read/carry)

### Business (1 tool)
30. `elara_business(action, ...)` — Idea/compete/score/update/list/review/link/stats/boot

### LLM (1 tool)
31. `elara_llm(action, ...)` — Local Ollama: status/query/classify/summarize/triage

### Maintenance (3 tools)
32. `elara_rebuild_indexes(collection?)` — Rebuild ChromaDB collections
33. `elara_briefing(action, ...)` — RSS feeds: today/search/add/remove/fetch/stats
34. `elara_snapshot()` — Full state-of-the-world snapshot

---

## Data Storage Layout

```
~/.claude/
├── elara-state.json                  # Current emotional state (mood, session, imprints)
├── elara-presence.json               # Presence tracking
├── elara-mood-journal.jsonl          # Historical mood entries
├── elara-imprint-archive.jsonl       # Archived imprints
├── elara-temperament-log.jsonl       # Temperament adjustments
├── elara-handoff.json                # Session handoff (plans, reminders, promises)
├── elara-context.json                # Quick context
├── elara-goals.json                  # Goal list
├── elara-corrections.json            # Correction list (never decays)
├── elara-intention.json              # Growth intention
├── elara-daemon.log                  # Central daemon log
├── elara-feeds.json                  # RSS feed configs
│
├── elara-memory-db/                  # ChromaDB: semantic memories (cosine)
├── elara-conversations-db/           # ChromaDB: conversation exchanges (cosine)
│   └── ingested.json                 # Ingestion manifest
├── elara-episodes-db/                # ChromaDB: searchable milestones (cosine)
├── elara-reasoning-db/               # ChromaDB: reasoning trails (cosine)
├── elara-corrections-db/             # ChromaDB: corrections (cosine)
├── elara-synthesis-db/               # ChromaDB: synthesis + seeds (cosine)
├── elara-briefing-db/                # ChromaDB: RSS items (cosine)
│
├── elara-dreams/
│   ├── status.json
│   ├── weekly/{YYYY-W##}.json
│   ├── monthly/{YYYY-MM}.json
│   ├── threads/{YYYY-MM}.json
│   └── emotional/{YYYY-W##-emotional}.json
│
├── elara-episodes/
│   ├── index.json
│   └── {YYYY-MM}/{episode_id}.json
│
├── elara-reasoning/{trail_id}.json
├── elara-outcomes/{outcome_id}.json
├── elara-ideas/{idea_id}.json
├── elara-synthesis/{synthesis_id}.json
├── elara-reflections/latest.json
│
├── overwatch-inject.txt              # Cross-reference injection (hook file)
├── overwatch-session-state.json      # Overwatch daemon state
│
└── projects/{project}/
    └── *.jsonl                       # Claude Code session transcripts
```

---

## ChromaDB Collections (7)

| Collection | DB Directory | Content | ~Size |
|-----------|-------------|---------|-------|
| `elara_memories` | elara-memory-db | Semantic memories + emotion tags | ~70 |
| `elara_conversations_v2` | elara-conversations-db | Session exchanges (user+assistant pairs) | ~1080 |
| `elara_milestones` | elara-episodes-db | Episode milestones | ~12 |
| `elara_corrections` | elara-corrections-db | Mistake patterns | ~3 |
| `elara_reasoning` | elara-reasoning-db | Problem-solving trails | varies |
| `elara_synthesis` + `elara_synthesis_seeds` | elara-synthesis-db | Recurring ideas + seed quotes | varies |
| `elara_briefing` | elara-briefing-db | RSS feed items | varies |

All collections use cosine similarity. Clients are cached at module level to avoid re-creation.

---

## Key Design Patterns

1. **Pydantic Everywhere** — All JSON validated on load/save. `extra="allow"` for forward compat.
2. **Atomic Writes** — Write .tmp → fsync() → rename() for crash safety.
3. **Event Bus** — Loose coupling. 35+ event types. Thread-safe with Lock.
4. **Module-Level ChromaDB Caching** — One client per module, lazy-initialized.
5. **Mood-Congruent Retrieval** — Memories tagged with emotion, biased by current mood on recall.
6. **Decay Mechanics** — Mood, imprints, residue all decay toward baseline over time.
7. **Temperament Growth** — Personality slowly adapts (max +/- 0.03/week), with factory decay.
8. **Overwatch Injection** — Daemon tails session JSONL, injects cross-references via hook file.
9. **Custom Exceptions** — `ElaraNotFoundError`/`ElaraValidationError` raised in daemon, caught in MCP tools.
10. **Mixin Architecture** — Overwatch uses 4 mixins (Parser, Search, Ingest, Snapshot).

---

## Dependencies

```
chromadb>=0.4.0          # Vector database
flask>=3.0.0             # Web interface
pydantic>=2.0.0          # Schema validation
python-dateutil>=2.8.0   # Date utilities
psutil>=5.9.0            # System monitoring
mcp[cli]>=1.0.0          # MCP server framework (FastMCP)
```

---

## Entry Points

```bash
# MCP server (Claude Code integration)
python3 -m elara_mcp.server

# Overwatch daemon (live session monitoring)
python3 -m daemon.overwatch

# Boot check
~/.claude/elara-boot.sh
```

---

## What We'd Like Reviewed

1. **Architectural coherence** — Do the module boundaries make sense? Any odd coupling?
2. **Data flow** — Is the event bus + direct calls + ChromaDB + JSON files approach sound?
3. **Reliability** — We just added atomic fsync, ChromaDB caching, seek bounds checks. What else?
4. **Scalability concerns** — 7 ChromaDB collections, growing JSON files, JSONL journals.
5. **Testing gap** — Zero automated tests. What should be tested first?
6. **Any anti-patterns** you spot in the design.
