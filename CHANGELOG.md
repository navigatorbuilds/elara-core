# Changelog

All notable changes to Elara Core.

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
