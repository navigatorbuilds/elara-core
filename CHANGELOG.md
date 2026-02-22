# Changelog

All notable changes to Elara Core.

## [0.17.0] — 2026-02-22

### Added — Awareness Engine v2
- **Boot/normal path split** — New sessions use chronological recall (recency-weighted) instead of semantic search, fixing garbage results from vague greetings like "hello"
- **`build_boot_enrichment()`** — Dedicated boot path with `[BOOT]`, `[LAST-SESSION]`, `[RECENT-WORK]`, `[NEXT]` sections for session continuity
- **`get_recent_exchanges()`** — Pure recency-based conversation retrieval (0.95 recency weight) for boot context
- **`get_handoff_summary()`** — Rich last-session summary: session number, what was done, files changed, commits, mood, next plans
- **`get_next_action()`** — Extracts first concrete action from handoff instead of showing abstract goals on boot
- **Carry-forward decay** — Items carried for 14+ sessions are suppressed from automatic injection (still available via on-demand recall)
- **Session boundary detection** — 5-minute gap threshold with automatic cache clearing and conversation ingest on new sessions
- **Conversation recall expanded** — 8 results fetched (up from 3), 5 injected per prompt for richer same-day context
- **Compound query improvement** — Rolling message buffer + current context anchoring for better semantic matches
- **Staleness filters** — Intentions >24h and context >24h auto-suppressed from injection

### Fixed
- Semantic search on boot no longer returns irrelevant memories from vague prompts
- Repeated goal/carry-forward injection ("broken record" problem) eliminated
- Session caches now properly cleared on new session boundaries

### Stats
- 157 source files, ~39K lines Python, 240 tests, 46 MCP tools across 17 modules

---

## [0.16.1] — 2026-02-22

### Added — Goal Decision Injection (YES System)
- **Goal `decision` field** — stores what was decided (action/plan/judgment) for each goal
- **Goal `build_order` field** — explicit sequencing (1=first, 2=second, etc.)
- **Intention hook upgrade** — `[GOALS]` injection now shows numbered build order with decision context instead of bare pipe-separated titles
- **MCP tool upgrade** — `elara_goal` accepts `decision` and `build_order` params on add/update
- **Boot summary** — sorts by build_order, shows decision context

### Stats
- 157 source files, ~39K lines Python, 240 tests, 46 MCP tools across 17 modules

---

## [0.16.0] — 2026-02-21

### Added — Unified Decision Registry (UDR)
- **UDR** (`daemon/udr.py`) — SQLite-backed ledger of permanent verdicts (rejected/approved/failed/revisit)
- **`elara_udr` MCP tool** — record, check, scan, list, review, stats, boot, backfill (8 actions)
- **Hook integration** — `[DECISION-CHECK]` injection in intention-hook.py, O(1) entity keyword scan
- **Backfill** — auto-imports from corrections and outcomes into UDR
- **New event**: `DECISION_RECORDED`

### Stats
- 157 source files, ~39K lines Python, 240 tests, 46 MCP tools across 17 modules

---

## [0.15.1] — 2026-02-21

### Fixed — Security Hardening
- Input validation across 7 modules (goals, corrections, handoff, episodes, business, reasoning, outcomes)
- Path traversal guards, integer overflow checks, string length limits
- Pydantic strict validation on all user-facing inputs

---

## [0.15.0] — 2026-02-21

### Added — Tier System + Cognitive Continuity Chain
- **Tier system** (`core/tiers.py`) — 4 hardware deployment levels controlling which modules load at runtime
  - Tier 0 VALIDATE: Crypto + DAG only (IoT, embedded sensors, microcontrollers)
  - Tier 1 REMEMBER: + memory, episodes, goals, maintenance ($30 phones, low-RAM)
  - Tier 2 THINK: + mood, awareness, dreams, cognitive, cognition_3d, workflows, knowledge, business, llm, gmail (DEFAULT)
  - Tier 3 CONNECT: + network (full mesh participation)
  - API: `set_tier()`, `get_tier()`, `tier_permits()`, `get_permitted_modules()`, `tier_name()`
  - CLI: `elara serve --tier {0,1,2,3}` + `ELARA_TIER` env var
  - Wizard: new Step 5 for tier selection
- **Cognitive Continuity Chain** (`core/continuity.py`) — cryptographic proof of unbroken AI cognitive experience
  - Hash-chained, dual-signed (Dilithium3 + SPHINCS+) cognitive state snapshots in the DAG
  - CognitiveDigest captures: mood vector, memory/model/prediction/principle/correction counts, active goals, session count, allostatic load
  - Automatic checkpoints on 6 trigger events (session end, principle crystallized, model created, dream completed, brain thinking completed, significant mood change)
  - Rate limited: max 1 checkpoint per 5 minutes
  - Chain verification: `verify_chain()` walks DAG backwards, verifies parent links + signatures
  - CLI: `elara continuity status` + `elara continuity verify`
- **New events**: `TIER_CHANGED`, `CONTINUITY_CHECKPOINT`
- **New path**: `continuity_file` in `core/paths.py`

### Changed
- **Server imports** now tier-gated — modules only load if `tier_permits(module_name)` returns True
- Server prints tier info to stderr on startup: "Tier 2 (THINK) — 14 modules active"

### Stats
- 153 source files, ~37,400 lines Python, 222 tests, 45 MCP tools across 15 modules

---

## [0.14.0] — 2026-02-20

### Added — One-Line Install + Every Install is a Node
- Network node auto-starts with `elara serve` (background thread, non-blocking)
- `--no-node` flag to disable network node
- `--node-type` flag to override node type (leaf/relay/witness)
- Version check on startup (background, non-blocking)
- Network bootstrap with seed peers and config persistence

---

## [0.13.0] — 2026-02-20

### Added — Cortical Execution Model + Long-Range Memory
- **Cortical Execution Model** — 5-layer concurrent architecture for non-blocking tool dispatch
  - Layer 0 REFLEX: TTL-based hot cache with event-driven invalidation (`daemon/cache.py`)
  - Layer 1 REACTIVE: Dual-mode async event bus with recursion guard (`daemon/events.py` rewrite)
  - Layer 2 DELIBERATIVE: IO pool (4 threads) + LLM pool (2 threads) with backpressure (`daemon/workers.py`)
  - Layer 3 CONTEMPLATIVE: Brain events (BRAIN_THINKING_STARTED/COMPLETED) + cache invalidation
  - Layer 4 SOCIAL: Network ops consolidated onto MCP event loop
  - Async reactive processors (`daemon/reactive.py`) — context tracking, correction matching, mood-congruent updates
- **Async tool dispatch** — All 45 tool handlers automatically wrapped in `async def` + `run_in_executor`
- **Long-range memory** (`memory/temporal.py`) — Temporal sweep across 4 time windows (1-2 weeks, 2-4 weeks, 1-3 months, 3+ months)
- **Landmark memories** — Importance >= 0.9 tagged as landmarks, always surface at boot regardless of age
- **Boot temporal context** — Long-range memory digest injected at boot via `hooks/boot.py`
- **Timeline view** — `elara_episode_query(query="timeline")` shows top milestones across all time, grouped by month
- **77 new tests** across 5 test files (test_cache, test_async_tools, test_workers, test_reactive, test_temporal)

### Changed
- `elara_mcp/_app.py` — Tool decorator now wraps sync → async automatically via ThreadPoolExecutor
- `elara_mcp/tools/meta.py` — `elara_do` is now `async def` with executor dispatch
- `daemon/events.py` — Dual-mode bus: sync handlers inline, async handlers via `create_task()`
- `daemon/state_core.py` — Threading lock on state load/save for concurrent safety
- `daemon/mood.py` — Cache integration for `get_mood()`
- `daemon/presence.py` — Cache integration for `get_stats()`
- `daemon/overnight/scheduler.py` — Emits brain events
- `elara_mcp/tools/network.py` — Simplified async ops (no manual threading hacks)
- 2 new events: `BRAIN_THINKING_STARTED`, `BRAIN_THINKING_COMPLETED`
- 222 total tests (was 145)

## [0.12.0] — 2026-02-18

### Added — Layer 2 Testnet + Witness Persistence
- **Testnet script** (`scripts/testnet.py`) — 2+ node end-to-end proof: create record, exchange, witness, verify trust score
- **Testnet integration tests** (`tests/test_testnet.py`) — 4 tests covering status, exchange, witness, submit
- **CLI: `elara testnet`** — run N-node testnet demo with `--nodes`, `--port-base`, `--verbose`
- **Witness persistence** — SQLite-backed attestation store (was in-memory only), survives restarts
- **Attestation dedup via PRIMARY KEY** — `(record_id, witness_identity)` enforced at DB level

### Changed
- `WitnessManager` accepts optional `db_path` parameter; falls back to in-memory if not provided
- `NetworkServer` accepts `attestations_db` parameter, passed through to `WitnessManager`
- MCP `elara_network` start action now passes `attestations_db` path from `core.paths`
- Scheduler quiet hours log fixed (was crashing when quiet hours disabled)

## [0.11.0] — 2026-02-18

### Added — Layer 2 Network Stub + CLI Crypto Tools
- **Layer 2 network package** (`network/`) — minimum viable network with 6 files (~985 lines)
- **Peer discovery** — mDNS via zeroconf (zero-config LAN) + hardcoded peer lists (WAN)
- **Network server** — aiohttp HTTP endpoints: `POST /records`, `GET /records`, `POST /witness`, `GET /status`
- **Network client** — async HTTP client for all 4 server endpoints
- **Witness attestation** — counter-signing with dedup, in-memory attestation store
- **Trust scoring** — `T = 1 - 1/(1 + n)` formula (0 witnesses → 0.0, 3 → 0.75, 10 → 0.91)
- **`elara_network` MCP tool** — status, peers, start, stop, push, sync, witness (7 actions)
- **CLI: `elara sign <file>`** — dual-sign files with Dilithium3+SPHINCS+, write `.elara.proof`
- **CLI: `elara verify <proof>`** — verify signature + content hash from proof file
- **CLI: `elara identity`** — show identity hash, entity type, profile, key sizes
- **CLI: `elara dag stats`** — record count, edges, tips, roots, time range
- **Bridge hardening** — input validation, dedup cache (10K artifacts), sliding-window rate limit (120/min, env-configurable via `ELARA_BRIDGE_RATE_LIMIT`), `BridgeMetrics` dataclass with 6 counters, granular sign-vs-DAG error tracking

### Changed
- 6 new event types: `RECORD_RECEIVED`, `RECORD_WITNESSED`, `PEER_DISCOVERED`, `PEER_LOST`, `NETWORK_STARTED`, `NETWORK_STOPPED`
- 3 new paths: `network_config`, `network_peers`, `attestations_db`
- 45 MCP tools across 15 modules (was 44/14)
- Optional dependencies: `pip install elara-core[network]` (aiohttp, zeroconf)

## [0.10.8] — 2026-02-17

### Added — Layer 1 Bridge (Cryptographic Validation of Cognitive Artifacts)
- **Layer 1 Bridge** (`core/layer1_bridge.py`) — subscribes to Layer 3 event bus, creates signed Layer 1 validation records for significant cognitive events
- **Post-quantum dual signatures** — Dilithium3 + SPHINCS+ (Profile A) on every validated artifact
- **10 creation events validated** — model, prediction, principle, workflow, correction, dream, episode, handoff, synthesis, outcome
- **Local DAG storage** — SQLite-backed directed acyclic graph with parent chaining for causal history
- **Persistent AI identity** — generated once, reused across sessions, private keys protected (0600)
- **ELRA wire format** — byte-identical with Layer 1, Layer 1.5 (Rust), and hardware DAM spec
- **SOVEREIGN classification** — cognitive artifacts never leave the device by default
- **Optional dependency** — if `elara-protocol` not installed, bridge is dormant with zero impact

### Changed
- `ARTIFACT_VALIDATED` event type added to event bus
- `identity_file` and `dag_file` paths added to ElaraPaths
- MCP server initializes bridge at startup (silent fallback)

## [0.10.7] — 2026-02-17

### Added — Workflow Patterns (4th 3D Cognition Output)
- **Workflow Patterns** (`daemon/workflows.py`) — learned action sequences from episode history
- **Proactive surfacing** — mid-session observations detect when current task matches a known workflow trigger, surfaces remaining steps
- **Overnight detection** — new `workflow_detect` phase analyzes episode milestones for recurring multi-step processes
- **Confidence mechanics** — completion strengthens (+0.05), skip weakens (-0.03), auto-retire below 0.15
- **1 new MCP tool** (`elara_workflow`) — CRUD, semantic search, completion/skip tracking, stats
- **ChromaDB collection** `elara_workflows` for semantic activation matching

### Changed
- Overnight phases expanded from 14 to 15 (+ workflow_detect)
- 3D Cognition context in overnight brain now includes workflow data
- 44 MCP tools across 14 modules (was 43/13)

## [0.10.6] — 2026-02-17

### Added — Knowledge Graph
- **Knowledge Graph module** (`daemon/knowledge.py`) — document cross-referencing with 6-tuple addressing (semantic_id, time, source_doc, source_section, source_line, type)
- **SQLite backend** for structured node/edge/document storage
- **ChromaDB collection** `elara_knowledge` for semantic node search
- **4 validators** — internal consistency, cross-document contradiction detection, metric conflicts, dependency gaps
- **4 new MCP tools** (`elara_kg_index`, `elara_kg_query`, `elara_kg_validate`, `elara_kg_diff`)
- **Alias system** — maps variant names to canonical semantic IDs

### Changed
- 43 MCP tools across 13 modules (was 39/12)

## [0.10.0] — 2026-02-14

### Added — 3D Cognition System
- **Cognitive Models** (`daemon/models.py`) — persistent understanding that accumulates evidence, adjusts confidence, and decays over time
- **Predictions** (`daemon/predictions.py`) — explicit forecasts with deadlines, accuracy tracking, and calibration scoring
- **Principles** (`daemon/principles.py`) — crystallized rules from repeated insights, with confirmation and challenge mechanics
- **3 new MCP tools** (`elara_model`, `elara_prediction`, `elara_principle`) — full CRUD + search for all 3D layers
- **4 new overnight phases** — model_check, prediction_check, model_build, crystallize (structured JSON output parsed and applied)
- **Domain-aware confidence** — business patterns held at high confidence, human behavioral patterns held loosely
- **Time decay** — models not checked in 30 days lose confidence automatically

### Added — Creative Drift
- **Overnight drift mode** (`daemon/overnight/drift.py`) — the brain's imagination
- **5 creative techniques** — free association, inversion, metaphor, spark, letter to morning
- **Random context sampling** — pulls items from different knowledge categories for unexpected collisions
- **Creative journal** — accumulates drift output over time (never overwrites)
- **Higher temperature** (0.95) for looser, more creative LLM output

### Added — Scheduling & Morning Brief
- **Scheduled mode** — run every N hours regardless of session activity (alongside session-aware mode)
- **Morning brief** — concise summary written after each overnight run (TL;DR, prediction deadlines, brain activity, drift highlight)
- **Multi-scale temporal gathering** — daily, weekly, monthly aggregation of session data
- **Boot integration** — morning brief detection in boot-check.sh

### Changed
- Overnight phases expanded from 10 to 14 (+ drift rounds)
- Context gathering now includes 3D cognition data (models, predictions, principles)
- Thinker accepts raw context dict for structured JSON processing
- Findings include 3D Cognition Updates section
- Metadata includes cognition stats
- 38 MCP tools across 12 modules (was 35/11)

## [0.9.2] — 2026-02-08

### Added
- 34-page documentation site at elara.navigatorbuilds.com
- Interactive playground (try Elara without installing)
- Memory visualizer (canvas-based network animation)
- Interactive config generator with live JSON preview
- 6 community persona templates + recommendation quiz
- Typing speed test for MCP tool commands
- Ambient soundscape generator (Web Audio API)
- Matrix rain screensaver
- Cinematic origin story + CRT boot intro
- Development timeline with 16 milestones
- Competitor comparison (vs mem0, Letta, ChatGPT Memory)
- Module deep-dive documentation
- Python API reference with real signatures
- Printable CLI cheat sheet
- Use case showcase (6 examples)
- Before/after comparison page
- Migration guide (from mem0, ChatGPT, Obsidian)
- Performance benchmarks page
- FAQ/troubleshooting page
- Contributing guide
- Privacy policy (zero telemetry)
- License explainer (BSL-1.1 in plain language)
- Client-side search (lunr.js)
- Cmd+K command palette for doc navigation
- PWA support (offline caching, installable)
- Atom feed for releases
- 5 SVG sticker designs + gallery
- Public roadmap (4 phases)
- Status dashboard with live badges
- GitHub Actions CI (tests + link checker)
- Dependabot for auto dependency updates
- GitHub issue/PR templates
- FUNDING.yml for Sponsors
- security.txt (RFC 9116) + humans.txt
- GitHub Discussions with welcome post + templates
- 15 custom issue labels for all modules
- 3 good-first-issue starter issues
- PRs to 2 awesome-mcp-servers lists

## [0.9.1] — 2026-02-08

### Added
- GitHub Actions CI — tests run on every push (Python 3.12)
- Auto-publish to PyPI on version tags
- Custom domain: elara.navigatorbuilds.com
- OG preview images and JSON-LD structured data for SEO
- Tools reference page (34 tools documented)
- GitHub issue templates (bug report, feature request)
- SVG favicon

### Changed
- Homepage URL updated to custom domain in PyPI metadata
- README badge row: Tests, PyPI, License

### Fixed
- f-string nested quote syntax for CI compatibility

## [0.9.0] — 2026-02-07

### Added
- First public release on PyPI
- pip-installable package with CLI (`elara init`, `elara serve`)
- BSL-1.1 license
- 90 tests passing
- Cyberpunk landing page (GitHub Pages)
- Live terminal demo (asciinema)
- Setup guides for 6 MCP clients (Claude Code, Cursor, Windsurf, Cline, Zed, custom)

### Core Features (all modules)
- **34 MCP tools** across 11 modules
- **Semantic memory** — ChromaDB vector search, importance weighting, natural decay
- **Conversation indexing** — every exchange searchable by meaning
- **Episodic tracking** — sessions as episodes with milestones, decisions, mood arcs
- **Mood system** — valence, energy, openness with natural decay and personality modes
- **Dream processing** — weekly/monthly/emotional pattern discovery
- **Reasoning trails** — hypothesis chains, evidence tracking, dead ends, solutions
- **Corrections** — mistake tracking that never decays, boot-loaded
- **Goal tracking** — persistent goals with staleness detection
- **Business intelligence** — 5-axis idea scoring, competitor tracking, pitch analytics
- **Session handoff** — structured carry-forward between sessions
- **Self-awareness** — reflection, blind spots, relationship pulse, growth intentions
- **Gmail integration** — read, triage, send, archive, semantic search
- **Local LLM** — Ollama interface for classification, summarization, triage
- **Overwatch daemon** — background conversation watching, auto cross-references
- **RSS briefing** — external intelligence feeds with semantic search

## [Pre-release] — 2026-02-01 to 2026-02-06

### Development History
- 70 sessions over 6 days
- Architecture: monolith → split modules → mixin patterns
- Overwatch daemon rewrite (drop LLM hallucinations, use importance scoring)
- Pydantic schemas wired into 7 daemon modules
- Atomic write helpers, structured logging, custom exceptions
- 16 broad exception handlers narrowed to specific types
- ChromaDB caching, fsync, bounds checks (11 reliability fixes)
