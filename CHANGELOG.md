# Changelog

All notable changes to Elara Core.

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
