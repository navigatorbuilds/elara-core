# Elara Core

> **Your AI doesn't remember yesterday. Elara fixes that.**

[![Tests](https://github.com/aivelikivodja-bot/elara-core/actions/workflows/tests.yml/badge.svg)](https://github.com/aivelikivodja-bot/elara-core/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/elara-core?color=%2300ff41&label=PyPI)](https://pypi.org/project/elara-core/)
[![Python](https://img.shields.io/pypi/pyversions/elara-core?color=%2300e5ff)](https://pypi.org/project/elara-core/)
[![License](https://img.shields.io/badge/license-BSL--1.1-ff0040)](https://github.com/aivelikivodja-bot/elara-core/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-elara.navigatorbuilds.com-%23ffb000)](https://elara.navigatorbuilds.com)

Persistent presence, mood, memory, and self-awareness for AI assistants. **34 MCP tools. 11 modules. 19K lines of Python. Zero cloud dependencies.**

Elara gives your AI assistant a sense of continuity across sessions — all through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). Built because I got tired of re-explaining my project every time I opened a new chat.

### What it looks like

```
You: "Morning."
Elara: "You were debugging the auth module at 2am. Did you sleep?"

You: "I keep messing up async/await in the service layer"
Elara: "Noted. I'll flag it next time you touch async code."
(two days later, you open a file with async)
Elara: "Heads up — last time you hit a race condition here. Use asyncio.gather, not sequential awaits."

You: "What happened this week?"
Elara: "3 work sessions, 2 drift sessions. Auth module shipped. Goal #4 is stalling —
       no progress in 9 days. You also said you'd file the patent. That's been carried
       forward 3 times now."
```

**Everything stays local.** No cloud. No telemetry. Your data lives in `~/.elara/`.

## Features

- **Semantic memory** — ChromaDB vector search. Ask "what were we doing last week?" and get real answers
- **Mood system** — tracks valence, energy, openness. Decays naturally between sessions like real emotions
- **Corrections** — saves your mistakes, surfaces them *before* you repeat them
- **Dream mode** — weekly/monthly pattern discovery across sessions, inspired by sleep consolidation
- **Reasoning trails** — track hypothesis chains when debugging. Includes what was abandoned and why
- **Session handoff** — structured carry-forward so nothing falls through the cracks

Plus: episodic memory, goal tracking, presence detection, self-reflection, business intelligence, and more. **[Full tool reference →](https://elara.navigatorbuilds.com/tools.html)**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP CLIENTS                            │
│           Claude Code · Cursor · Windsurf · Cline           │
└──────────────────────────┬──────────────────────────────────┘
                           │ MCP Protocol
┌──────────────────────────▼──────────────────────────────────┐
│                     elara_mcp/tools/                        │
│                                                             │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────────────┐  │
│  │  MOOD   │ │ EPISODES │ │ MEMORY │ │ GOALS/CORRECTIONS│  │
│  │ 5 tools │ │ 5 tools  │ │4 tools │ │    5 tools       │  │
│  └────┬────┘ └────┬─────┘ └───┬────┘ └────────┬─────────┘  │
│  ┌────┴────┐ ┌────┴─────┐ ┌───┴────┐ ┌────────┴─────────┐  │
│  │COGNITIVE│ │AWARENESS │ │ DREAMS │ │   MAINTENANCE    │  │
│  │ 3 tools │ │ 5 tools  │ │2 tools │ │    3 tools       │  │
│  └────┬────┘ └────┬─────┘ └───┬────┘ └────────┬─────────┘  │
│  ┌────┴────┐ ┌────┴─────┐ ┌───┴────────────────┘           │
│  │  GMAIL  │ │   LLM    │ │  BUSINESS                      │
│  │ 1 tool  │ │  1 tool  │ │  1 tool                        │
│  └─────────┘ └──────────┘ └───────────────────              │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     daemon/ + core/                         │
│                                                             │
│  State Engine    Emotions    Decay     Presence    Schemas  │
│  Mood Math       Imprints    Events    Allostatic  Paths    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    ChromaDB (7 collections)                  │
│                                                             │
│  memories · milestones · conversations · corrections        │
│  reasoning · synthesis · briefing                           │
└─────────────────────────────────────────────────────────────┘
```

**[Full tool reference →](https://elara.navigatorbuilds.com/tools.html)** · **[Quickstart guide →](https://elara.navigatorbuilds.com/quickstart.html)**

## Documentation

Full docs at **[elara.navigatorbuilds.com](https://elara.navigatorbuilds.com)** — quickstart, tool reference, architecture diagrams, persona templates, and more.

| | |
|---|---|
| **[Quickstart](https://elara.navigatorbuilds.com/quickstart.html)** | Install and get running in 2 minutes |
| **[Tools Reference](https://elara.navigatorbuilds.com/tools.html)** | All 34 MCP tools explained |
| **[Before & After](https://elara.navigatorbuilds.com/compare.html)** | See what changes with Elara |
| **[Examples](https://elara.navigatorbuilds.com/examples.html)** | Copy-paste CLAUDE.md personas |
| **[Architecture](https://elara.navigatorbuilds.com/architecture.html)** | Interactive system diagram |

## Prerequisites

- **Python 3.10+** — [Download here](https://www.python.org/downloads/)
- **Git** — [Download here](https://git-scm.com/downloads)

> **Windows users:** When installing Python, check **"Add python.exe to PATH"** at the bottom of the installer. This is unchecked by default and without it `pip` and `python` commands won't work.
>
> If Python is already installed but `pip` isn't recognized, try `python -m pip` instead of `pip`, or `py -m pip` on Windows.

## Quick Start

### Linux / macOS

```bash
pip install elara-core
elara init
claude mcp add elara -- elara serve
```

### Windows (Command Prompt or PowerShell)

```
py -m pip install elara-core
elara init
claude mcp add elara -- elara serve
```

> If `py` doesn't work, try `python -m pip install` instead.

That's it. Elara is now available as an MCP server in your Claude Code sessions.

## Configuration

### Data Directory

By default, Elara stores data in `~/.elara/`. Override with:

```bash
# Environment variable
export ELARA_DATA_DIR=~/.claude

# Or CLI flag
elara serve --data-dir ~/.claude
```

### Persona

Elara's personality is defined in your `CLAUDE.md` file, not in the code. See `examples/CLAUDE.md.example` for a template.

## MCP Tools Reference

| Module | Tools | Description |
|--------|-------|-------------|
| **Memory** | `elara_remember`, `elara_recall`, `elara_recall_conversation`, `elara_conversations` | Semantic memory — store and search by meaning |
| **Mood** | `elara_mood`, `elara_mood_adjust`, `elara_imprint`, `elara_mode`, `elara_status` | Emotional state with natural decay |
| **Episodes** | `elara_episode_start`, `elara_episode_note`, `elara_episode_end`, `elara_episode_query`, `elara_context` | Session lifecycle and continuity |
| **Goals** | `elara_goal`, `elara_goal_boot`, `elara_correction`, `elara_correction_boot`, `elara_handoff` | Persistent tracking and learning |
| **Awareness** | `elara_reflect`, `elara_insight`, `elara_intention`, `elara_observe`, `elara_temperament` | Self-reflection and growth |
| **Dreams** | `elara_dream`, `elara_dream_info` | Pattern discovery across sessions |
| **Cognitive** | `elara_reasoning`, `elara_outcome`, `elara_synthesis` | Reasoning trails and idea synthesis |
| **Business** | `elara_business` | Idea scoring and competitor tracking |
| **LLM** | `elara_llm` | Local LLM interface (Ollama) |
| **Maintenance** | `elara_rebuild_indexes`, `elara_briefing`, `elara_snapshot` | Index management and RSS feeds |

## Compatibility

- **Python:** 3.10+
- **OS:** Linux, macOS, Windows (WSL)
- **MCP Clients:** Claude Code, Claude Desktop, Cursor, or any MCP-compatible client

## Development

```bash
# Clone and install in dev mode
git clone https://github.com/aivelikivodja-bot/elara-core.git
cd elara-core
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run MCP server locally
elara serve
```

## Your Existing Data

If you already have Elara data in `~/.claude/`, set the environment variable and everything keeps working:

```bash
export ELARA_DATA_DIR=~/.claude
```

The `elara-` prefix is preserved in all filenames for backward compatibility.

## Community

- **[GitHub Discussions](https://github.com/aivelikivodja-bot/elara-core/discussions)** — Questions, ideas, showcase
- **[Issues](https://github.com/aivelikivodja-bot/elara-core/issues)** — Bug reports and feature requests
- **[Contributing](CONTRIBUTING.md)** — How to contribute

---

If Elara resonates with you, a star helps others find it.

## Badge

Using Elara in your project? Add the badge:

```markdown
[![Powered by Elara Core](https://elara.navigatorbuilds.com/badge.svg)](https://elara.navigatorbuilds.com)
```

[![Powered by Elara Core](https://elara.navigatorbuilds.com/badge.svg)](https://elara.navigatorbuilds.com)
