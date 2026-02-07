# Claude Architecture Review — 2026-02-07

## Source
Full architecture document (`~/elara-architecture-review.md`) was given to Claude (web) for review.
Extra question added: "How to make Elara a business partner?"

## What They Said Was Strong
- 3D mood space with exponential decay toward driftable temperament — "elegant"
- Imprint system (persistent emotional residue that fades) — "smart abstraction"
- Mood-congruent memory retrieval — "standout feature, mirrors how human memory works"
- Overwatch daemon — "well-thought-out infrastructure"
- Atomic writes everywhere — "good discipline"

## Architectural Concerns (Ordered by Severity)

### 1. God-Module Problem (HIGH)
- self_awareness.py (1,054 lines) reads from 6+ modules
- dream.py (1,089 lines) same issue
- **Fix:** Extract `daemon/snapshot.py` — standardized "state of the world" object consumed by both

### 2. ChromaDB Boundary Blur (MEDIUM)
- JSON = source of truth, ChromaDB = index — but boundary is blurry in some modules
- corrections.py: JSON is source, but "loud failure" on ChromaDB = operational dependency
- **Fix:** `elara_rebuild_indexes` command to reconstruct all 6 collections from sources

### 3. Too Many Storage Locations (MEDIUM)
- 10+ JSON files, 3 JSONL, 6+ directories, 6 ChromaDB collections
- No manifest describing complete state
- **Fix:** `manifest.json` + `elara_export` / `elara_import` for snapshot/restore

### 4. Overwatch Injection Fragility (LOW)
- File-based side-channel (/tmp/) can silently fail
- **Fix:** Staleness check (injection file >N minutes old = something wrong)

### 5. Session Type Auto-Detection Too Rigid (LOW)
- Time-of-day only. Weekend mornings ≠ work. Late-night debugging ≠ drift.
- **Fix:** Time as prior, update based on actual activity in first few exchanges

## File Split Suggestions
- **conversations.py (917):** Split into parser + indexer + search (3 files)
- **self_awareness.py (1,054):** Extract 7 proactive detectors → `daemon/patterns.py`
- **dream.py (1,089):** Split into dream_weekly.py + dream_emotional.py + coordinator

## Cognitive Layer Gaps
- **Contradiction detection:** Nothing flags when new decision contradicts a previous lesson
- **Confidence calibration:** Not computing "when Elara predicts X with high confidence, she's right Y% of the time"

## Business Partner Recommendations
- Market/idea tracking on reasoning.py + synthesis.py
- Pitch refinement loop using outcomes tracking with fails_when/fine_when
- Decision urgency modeling with expiration dates in handoff
- External knowledge ingestion via RSS feeds (zero Claude tokens if using local embeddings)
- "The architecture already supports most of this — you mainly need a domain-specific layer on top"

## Security Note
- ChromaDB + JSON files are world-readable on filesystem
- Not a concern for localhost, but encrypt at rest if ever exposed beyond local

## Overall Assessment
"Well beyond hobby-project quality. Emotional modeling is thoughtful, architecture is clean where it matters, operational patterns show real engineering discipline."

## Action Plan
→ See `docs/business-partner-spec.md` for full build spec (approved, 2 sessions)
