# Kimi Architecture Review #2 — 2026-02-07

## Source
Updated architecture doc (57 files, 14,307 lines, 30 tools) reviewed by Kimi.
Includes business partner layer, pitch tracking, decision urgency.

## Key Recommendations

### Architecture
1. **Split self_awareness.py into awareness/ package** — reflect.py, pulse.py, blind_spots.py, proactive.py. Analysis is on-demand, observation is continuous — different cadences.
2. **God Object risk in core/elara.py** — at 200 files becomes bottleneck. Extract StateManager, SessionCoordinator, MemoryOrchestrator.
3. **Configuration sprawl** — constants scattered (decay rates in state_core, thresholds in priority, resonance weights in vector). Single config.py or TOML file.

### Emotional System
4. **Mode switches should decay** — modes should be session contexts, not permanent overrides. Or log as high-strength imprints. Two risks: mode amnesia (never auto-reverts) and temperament contradiction (mode vs baseline).
5. **Imprint type-specific decay** — connection imprints should decay slower (0.9x rate) or have lower archive threshold (0.05). Currently all types decay identically.
6. **Allostatic load unused** — should accumulate from frequent adjustments, negative sessions, late nights. Temporarily shifts temperament baseline.

### Business Layer
7. **Keep file-based** — migrate at semantic search need or ~500 ideas
8. **Pitch coupling is correct** — "pitches ARE decisions with outcomes". Storage coupled, analysis specialized (separate pitch.py for analytics)
9. **Missing: idea relationship mapping** — "this competes with that" or "these are variants of same problem"
10. **Missing: resource conflict detection** — two ideas needing full attention simultaneously = impossible
11. **Missing: pivot suggestions** — if idea A has 3 failed pitches and idea B similar has 2 wins, suggest pivoting A toward B's framing

### User-State Modeling
12. **Passive inference only** — mood adjustments, session type patterns, response latency, goal staleness
13. **Store inferences with confidence, not facts** — "possible_stress: 0.7" not "user is stressed"
14. **Session-local or encrypted** — user state should not persist raw, or if persisted, user-accessible
15. **Output is suggested_approach, not diagnosis** — "gentle", "energetic", etc.

### Priority Scoring Edge Cases
16. **Zombie item problem** — item carried 10x over 3 months decays to zero. Cap decay at 0.3 minimum, or add importance flag that bypasses decay.
17. **Expiry should override carry decay** — use max(expiry_score, decayed_carry_score), not additive
18. **Time-of-day should modulate, not add** — base_score * time_multiplier instead of base_score + time_adjustment

### Layer Interaction Model
19. **Emotional modulates all** — tone, urgency, risk tolerance
20. **Cognitive provides structure** — hypothesis testing, decision tracking
21. **Business generates stakes** — excitement, anxiety feeds back as imprints
22. **Specific: failed pitch → negative imprint**
23. **Specific: low valence → inflate effort estimates (pessimism bias)**
24. **Specific: many abandoned approaches in reasoning → suggest simpler framing**

### Security
25. **Overwatch injection in /tmp** — any process can write here. Verify with timestamp or checksum.
26. **503 for missing secret leaks service existence** — consider 404 (minor)
27. **chmod 700 on elara directories** — standard user data protection

### Priority Order
1. Overwatch LLM layer (Ollama)
2. User state inference
3. Episode compression
4. Mode decay
5. Goal conflict detection
6. Allostatic load activation

## Notable Quote
"You've built something rare: a system with coherent philosophy. The emotional decay curves, the bounded temperament drift, the distinction between imprints and moods—these aren't arbitrary features, they're a model of psyche."

## Key Question From Kimi
"When you run elara_reflect, does it surprise you? Or does it confirm what you already felt? The measure of a mirror isn't whether it's accurate, but whether it shows you something you couldn't see yourself."
