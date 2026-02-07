# Claude Architecture Review #2 — 2026-02-07

## Source
Updated architecture doc (57 files, 14,307 lines, 30 tools) reviewed by Claude (web).
Includes business partner layer, pitch tracking, decision urgency.

## Key Recommendations

### Architecture
1. **Split big files now** — conversations.py (Searcher/Ingester/CrossReferencer), self_awareness.py (each lens its own file under self_awareness/ package)
2. **Event bus** — mood_changed, episode_ended, goal_stalled events for decoupling. Sets up Overwatch LLM layer (subscribe to events vs parse JSONL)
3. **Schema registry** — single schemas.py with dataclasses/Pydantic for all JSON structures. Catches drift early.

### Emotional System
4. **Mood oscillation risk** — add refractory period after significant shift (delta > 0.3), dampen further shifts temporarily
5. **Allostatic load is dead weight** — accumulated stress should reduce openness and energy baselines temporarily. Currently unused in schema.
6. **Temperament drift caps should be per-dimension** — openness might reasonably drift more than valence. Currently uniform ±0.15.

### Business Layer
7. **Keep file-based until 50-100 ideas** — trigger is semantic search need, not count
8. **Pitch coupling is pragmatic** — extract PitchTracker class when pitch-specific fields outnumber shared fields
9. **Missing: validation tracking** — structured way to record "talked to 5 people, 3 would pay"
10. **Missing: time-to-validate metric** — how long in "exploring" with no evidence = zombie idea
11. **Missing: revenue/effort ratio** — compare expected return per hour invested

### User-State Modeling
12. **Infer, don't ask** — message length, response time, topic shifts, question frequency, emoji usage, session duration
13. **Map to lightweight model:** engagement, energy, topic_focus, mood_signal
14. **Adapt without saying** — shorter responses when engagement drops, lighter tone when energy low

### Priority Scoring Edge Cases
15. **Long_horizon flag** — pauses velocity decay for legitimately long-term items
16. **EXPIRED should bypass time-of-day adjustments** — if it's past deadline, late night doesn't matter
17. **Scores >120 stack correctly** — verify display logic handles gracefully

### Security
18. **Move injection file out of /tmp** — world-readable, any process can read/write
19. **ELARA_SECRET needs rotation mechanism + session management**
20. **ChromaDB is world-readable** — fine for localhost, encrypt at rest if ever exposed

### Priority Order
1. Schema validation (Pydantic)
2. Split the three large files
3. Move injection file out of /tmp
4. Wire up allostatic load
5. Add event bus
6. User-state inference
