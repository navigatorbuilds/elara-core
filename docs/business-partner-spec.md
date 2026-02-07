# Elara Business Partner Layer — Build Spec

## Created: 2026-02-07 (Session 55)
## Status: APPROVED, ready to build

---

## Overview

Add business intelligence capabilities to Elara using existing primitives (reasoning, synthesis, outcomes, handoff, priority). Four modules, ~930 lines total, 2 sessions to build.

---

## Module 1: `daemon/business.py` (~350 lines)

### Purpose
Business idea tracking with competitive landscape, viability scoring, and hypothesis chains. Wraps reasoning.py + synthesis.py + outcomes.py with business vocabulary.

### Functions
- `create_idea(name, description, target_audience, your_angle, tags)` — New business idea
- `add_competitor(idea_id, name, strengths, weaknesses, url)` — Track competitors
- `score_idea(idea_id, problem, market, effort, monetization, fit)` — 5-axis scoring (/25)
- `update_idea(idea_id, status, notes)` — Status: exploring/validated/building/launched/abandoned
- `get_idea(idea_id)` — Full idea with competitors + score + linked reasoning trails
- `list_ideas(status, min_score)` — Filter/list ideas
- `link_to_reasoning(idea_id, trail_id)` — Connect idea to reasoning trail
- `link_to_outcome(idea_id, outcome_id)` — Connect idea to decision outcome
- `boot_summary()` — Active ideas, approaching deadlines, stale ideas

### Data Structure
```json
{
  "idea_id": "handybill-spinoffs",
  "name": "HandyBill Standalone Spinoffs",
  "description": "3 standalone apps from HandyBill code",
  "target_audience": "freelancers, sole traders",
  "your_angle": "dead simple, no subscription, offline-first",
  "competitors": [
    {"name": "Wave", "strengths": "free, established", "weaknesses": "complex, online-only", "url": "wave.com"}
  ],
  "score": {"problem": 4, "market": 3, "effort": 4, "monetization": 3, "fit": 5, "total": 19},
  "status": "exploring",
  "tags": ["handybill", "play-store", "monetization"],
  "reasoning_trails": [],
  "outcomes": [],
  "created": "ISO",
  "last_touched": "ISO",
  "notes": []
}
```

### Storage
- `~/.claude/elara-business/` (one JSON per idea)
- No ChromaDB needed (small dataset, direct lookup)

### MCP Tool: `elara_business`
- Actions: `idea` (create), `compete` (add competitor), `score`, `update`, `list`, `review` (full idea report), `boot` (summary)
- Parameters: action, idea_id, name, description, target_audience, your_angle, competitor_name, strengths, weaknesses, url, problem, market, effort, monetization, fit, status, notes, tags, min_score

### Token Cost
- ~0 at rest
- ~200-400 tokens per query
- ~600-1,200 tokens/session when actively discussing business

---

## Module 2: Pitch Refinement (extends `daemon/outcomes.py`, ~100 lines)

### Purpose
Track pitch attempts as outcomes with business-specific metadata. Learn what framing works.

### Changes to outcomes.py
- Add optional `pitch_metadata` field to outcome structure:
  ```json
  {
    "channel": "reddit",
    "audience": "r/freelance",
    "framing": "problem-story",
    "response_metric": "downloads"
  }
  ```
- `record_pitch(idea_id, channel, audience, framing, predicted, tags)` — Convenience wrapper
- `get_pitch_stats(idea_id)` — Win rate by channel, by framing
- `get_pitch_lessons(idea_id)` — Corrections that apply to this idea's pitches

### Storage
- Same `~/.claude/elara-outcomes/` directory (outcomes with pitch_metadata field)
- No new storage locations

### Token Cost
- ~200 tokens per record
- ~400 tokens per review
- ~600-1,200 tokens/session when actively marketing

---

## Module 3: Decision Urgency (extends `daemon/handoff.py` + `daemon/priority.py`, ~80 lines)

### Purpose
Add expiration dates to handoff items. Priority engine scores approaching deadlines higher.

### Changes to handoff.py
- Add optional `expires` field to item schema:
  ```json
  {"text": "Submit privacy policy", "carried": 0, "first_seen": "ISO", "expires": "ISO"}
  ```
- `validate_handoff()` — accept expires field (optional ISO timestamp)
- No other changes needed

### Changes to priority.py
- `compute_priority()` — if item has `expires`:
  - <24h remaining: score +30 (URGENT)
  - <72h remaining: score +15
  - Expired: flag as EXPIRED (still show, different formatting)
- `_format_brief()` — show expiration warnings:
  ```
  [Priority] ⏰ EXPIRING SOON: Submit privacy policy (12h left)
  [Priority] ⚠ EXPIRED: Google Play listing window (2 days ago)
  ```

### Token Cost
- ~50 extra tokens at boot
- Negligible

---

## Module 4: External Briefing (`daemon/briefing.py` ~250 lines + cron script ~150 lines)

### Purpose
Ingest external signals (RSS feeds, competitor data) and surface relevant items during sessions. Runs outside Claude — zero token cost for ingestion.

### `daemon/briefing.py` — Briefing engine
- `add_feed(name, url, category, keywords)` — Configure RSS feed
- `remove_feed(name)` — Remove feed
- `list_feeds()` — Show configured feeds
- `fetch_all()` — Fetch all feeds, extract new items
- `get_briefing(n, category)` — Today's highlights (for boot)
- `search_briefing(query, n)` — Semantic search through briefing items
- `get_briefing_stats()` — Feed health (last fetch, error count, items)

### Feed Item Structure
```json
{
  "item_id": "hash",
  "feed_name": "Flutter Blog",
  "category": "tech",
  "title": "Flutter 3.29 Released",
  "summary": "Breaking changes in...",
  "url": "https://...",
  "published": "ISO",
  "fetched": "ISO",
  "keywords_matched": ["flutter"],
  "relevance_score": 0.8
}
```

### Storage
- Config: `~/.claude/elara-feeds.json` (feed definitions)
- Items: `~/.claude/elara-briefing-db/` (ChromaDB collection, cosine)
- Today's brief: `~/.claude/elara-briefing.json` (pre-computed for boot)

### ChromaDB Collection
- Name: `elara_briefing`
- Distance: cosine
- Metadata: feed_name, category, published, keywords_matched

### Cron Script: `scripts/elara-briefing.py`
- Standalone Python script (no Claude dependency)
- Uses `feedparser` library for RSS/Atom
- Uses ChromaDB's default embedding function (local, free)
- Runs daily via cron: `0 8 * * * /home/neboo/elara-core/venv/bin/python /home/neboo/elara-core/scripts/elara-briefing.py`
- Writes briefing.json with top items for boot

### MCP Tool: `elara_briefing`
- Actions: `today` (boot briefing), `search` (semantic search), `feeds` (list/add/remove feeds), `fetch` (manual trigger)
- Parameters: action, query, n, feed_name, url, category, keywords

### Suggested Initial Feeds
- Flutter blog (official)
- Dart blog (official)
- Hacker News (filtered: flutter, dart, solo dev, indie hacker)
- r/FlutterDev (via RSS)
- Play Store Developer blog
- Competitor monitoring (Wave, Zoho, FreshBooks release pages)

### Boot Integration
- `hooks/boot.py` reads `elara-briefing.json`
- Prints 3-5 lines max:
  ```
  [Briefing] Flutter 3.29 released — check breaking changes
  [Briefing] Wave added mileage tracking (competitor)
  [Briefing] 2 new HandyBill reviews on Play Store
  ```

### Token Cost
- Ingestion: 0 Claude tokens (runs standalone)
- Boot summary: ~100-200 tokens
- Mid-session search: ~200-400 tokens per query

---

## Also Build (from Claude review)

### `elara_rebuild_indexes` tool (~200 lines in existing modules)
- Single command to rebuild all 6+ ChromaDB collections from JSON/JSONL sources
- Collections: memories, milestones, conversations, corrections, reasoning, synthesis, briefing
- Add to cognitive.py or create maintenance.py

### `daemon/snapshot.py` (~150 lines)
- Produces standardized "state of the world" object
- Consumed by self_awareness.py and dream.py instead of each reaching into 6+ modules
- Reduces coupling, makes testing easier

---

## Token Budget (Total Per Session)

| Component | Tokens/Session | % of 200k |
|-----------|---------------|-----------|
| Current emotional/memory overhead | ~2,000-5,000 | 1-2.5% |
| Business idea queries (2-3/session) | ~600-1,200 | 0.3-0.6% |
| Pitch tracking | ~400-800 | 0.2-0.4% |
| Decision urgency (boot) | ~50 | ~0% |
| Daily briefing (boot) | ~100-200 | ~0.1% |
| **Total new** | **~1,150-2,250** | **~0.6-1.1%** |

---

## Build Order

### Session 1: Core Business Layer
1. `daemon/business.py` (~350 lines)
2. `elara_mcp/tools/business.py` MCP tool (~150 lines)
3. Pitch metadata in `daemon/outcomes.py` (~100 lines)
4. Expiry in `daemon/handoff.py` + `daemon/priority.py` (~80 lines)
5. Boot integration
6. Test all tools
7. Commit

### Session 2: External Briefing + Infrastructure
1. `daemon/briefing.py` (~250 lines)
2. `scripts/elara-briefing.py` cron script (~150 lines)
3. `elara_mcp/tools/business.py` add briefing actions
4. `daemon/snapshot.py` (~150 lines) — refactor self_awareness + dream to use it
5. `elara_rebuild_indexes` tool (~200 lines)
6. Boot integration for briefing
7. Set up cron job
8. Test everything
9. Commit + push

### Total New Code: ~1,430 lines (was ~930 estimate, added snapshot + rebuild)
