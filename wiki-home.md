# Elara Core Wiki

Welcome to the Elara Core knowledge base.

## Quick Navigation

| Page | Description |
|------|-------------|
| [Quickstart](https://elara.navigatorbuilds.com/quickstart.html) | Installation and setup guide |
| [Tools Reference](https://elara.navigatorbuilds.com/tools.html) | All 34 MCP tools documented |
| [Architecture](https://elara.navigatorbuilds.com/architecture.html) | System architecture diagram |
| [Configure](https://elara.navigatorbuilds.com/configure.html) | Interactive config generator |
| [Personas](https://elara.navigatorbuilds.com/personas.html) | Community persona templates |
| [FAQ](https://elara.navigatorbuilds.com/faq.html) | Troubleshooting guide |
| [Roadmap](https://elara.navigatorbuilds.com/roadmap.html) | Public development roadmap |
| [Privacy](https://elara.navigatorbuilds.com/privacy.html) | Zero-telemetry privacy policy |

## Key Concepts

### Memory System
Elara uses ChromaDB for semantic memory storage. Memories are vectorized and searchable by meaning, not just keywords. The system stores 7 types of data: memories, milestones, conversations, corrections, reasoning trails, syntheses, and briefings.

### Persona Files
Your AI's personality is defined in a `persona.md` file. This controls greeting style, communication tone, role balance, and behavioral protocols. See [Personas](https://elara.navigatorbuilds.com/personas.html) for templates.

### Episodes
Episodes track work sessions — what happened, what was decided, what was learned. They enable session continuity and "remember last time" capabilities.

### Corrections
When the AI makes a mistake, corrections ensure it doesn't repeat. They persist across sessions and load at boot time.

### Dreams
Weekly and monthly "dream" processing discovers patterns across sessions — project momentum, mood trends, recurring themes.

## Resources

- [GitHub Repository](https://github.com/aivelikivodja-bot/elara-core)
- [Documentation Site](https://elara.navigatorbuilds.com)
- [PyPI Package](https://pypi.org/project/elara-core/)
- [GitHub Discussions](https://github.com/aivelikivodja-bot/elara-core/discussions)
- [Changelog](https://elara.navigatorbuilds.com/changelog.html)
