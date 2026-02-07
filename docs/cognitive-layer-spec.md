# Cognitive Layer — Build Spec

Agreed 2026-02-07. Additive only — zero emotional systems removed.

## Layer 1: Reasoning Trails (~400 lines)

**File:** `daemon/reasoning.py`
**MCP tools:** 2-3 new tools in a new `tools/reasoning.py` module

Track hypothesis → evidence → conclusion → outcome chains during complex tasks.

```python
# Storage: ~/.claude/elara-reasoning/
{
  "trail_id": "sha256[:16]",
  "started": "ISO timestamp",
  "context": "What we were trying to solve",
  "hypotheses": [
    {
      "h": "What we thought the problem was",
      "evidence": ["What supported this"],
      "confidence": 0.7,
      "outcome": "true | false | partial"
    }
  ],
  "abandoned_approaches": ["What we tried and dropped"],
  "final_solution": "What actually worked",
  "breakthrough_trigger": "What led to the solution (if unexpected)",
  "tags": ["async", "chromadb", "flutter"],
}
```

**MCP tools:**
- `elara_reasoning(action="start"|"hypothesis"|"abandon"|"solve"|"search", ...)` — manage trails
- Search: ChromaDB collection `elara_reasoning` (cosine), search by problem similarity before tackling new issues

**Integration:**
- blind_spots() checks for recurring problem types (same tags appearing in multiple trails)
- Boot: "You've solved 3 similar async issues — check trail X"

## Layer 2: Outcome Tracking (~300 lines)

**File:** `daemon/outcomes.py`
**MCP tools:** added to existing `tools/goals.py` module (1 new tool)

Link decisions to results. Close the learning loop.

```python
# Storage: ~/.claude/elara-outcomes/
{
  "outcome_id": "sha256[:16]",
  "decision": "What we decided",
  "context": "Why we decided it",
  "reasoning_trail": "trail_id (if exists)",
  "predicted": "What we expected to happen",
  "actual": "What actually happened",
  "assessment": "win | partial_win | loss | too_early",
  "lesson": "One-line takeaway",
  "tags": ["architecture", "flutter", "performance"],
  "recorded": "ISO timestamp",
}
```

**MCP tool:**
- `elara_outcome(action="record"|"check"|"list", ...)` — record outcomes, check past outcomes before similar decisions

**Integration:**
- blind_spots() surfaces patterns: "You tend to overestimate X" if multiple losses share tags
- Dreams can reference: "3 decisions this week, 2 wins, 1 partial"

## Layer 3: Idea Synthesis (~350 lines)

**File:** `daemon/synthesis.py`
**MCP tools:** added to existing `tools/awareness.py` module (1 new tool)

Detect recurring half-formed ideas across sessions.

```python
# Storage: ~/.claude/elara-synthesis/
{
  "synthesis_id": "sha256[:16]",
  "concept": "Short name for the emerging idea",
  "seeds": [
    {
      "source": "conversation | memory | episode",
      "source_id": "id",
      "quote": "The actual words that hinted at this",
      "date": "ISO date",
    }
  ],
  "times_surfaced": 3,
  "first_seen": "ISO date",
  "last_reinforced": "ISO date",
  "status": "dormant | activated | implemented | abandoned",
  "confidence": 0.8,
}
```

**Detection approach (simpler than full LLM):**
- On conversation ingest: cluster new exchanges against existing synthesis seeds by cosine similarity
- If 3+ exchanges from different sessions cluster together → create synthesis
- Threshold: cosine similarity > 0.75 between seed quotes

**MCP tool:**
- `elara_synthesis(action="check"|"list"|"activate"|"abandon")` — surface ideas, mark as acted on

**Integration:**
- Boot: "Recurring idea: [concept] (surfaced 4 times over 2 weeks). Ready to build?"
- Dreams: weekly dream includes "emerging ideas" section

## Architecture

- 3 new daemon files (~1,050 lines total)
- 2-3 new MCP tools (total goes from 26 to 28-29)
- 1-2 new ChromaDB collections (reasoning, synthesis)
- Zero files deleted, zero emotional systems modified
- Final system: ~13,000 lines, emotional + analytical

## Build Order

1. reasoning.py + MCP tool (standalone, no deps)
2. outcomes.py + MCP tool (optional link to reasoning trails)
3. synthesis.py + MCP tool (uses conversations.py for seeds)
4. Wire into blind_spots() and dreams
5. Test in real session

## What We're NOT Building (decided)

- Adversarial mode (just be more direct)
- Execution modes (premature, emotional modes stay)
- Dependency graph (overkill at current scale, add blocked_by to goals instead)
- Breakthrough mechanism (research concept, not practical yet)
