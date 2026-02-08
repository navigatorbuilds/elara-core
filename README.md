# Elara Core

**[elara.navigatorbuilds.com](https://elara.navigatorbuilds.com)**

[![Tests](https://github.com/aivelikivodja-bot/elara-core/actions/workflows/tests.yml/badge.svg)](https://github.com/aivelikivodja-bot/elara-core/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/elara-core?color=%2300ff41&label=PyPI)](https://pypi.org/project/elara-core/)
[![License](https://img.shields.io/badge/license-BSL--1.1-ff0040)](https://github.com/aivelikivodja-bot/elara-core/blob/main/LICENSE)

Persistent presence, mood, memory, and self-awareness for AI assistants.

Elara gives your AI assistant a sense of continuity across sessions. It remembers what you were working on, tracks emotional state, learns from mistakes, and builds semantic memory — all through the Model Context Protocol (MCP).

## Features

- **Presence tracking** — knows when you're here, how long you've been gone
- **Mood and emotional state** — valence, energy, openness with natural decay
- **Semantic memory** — ChromaDB-backed vector search across conversations
- **Episodic memory** — session tracking with milestones, decisions, insights
- **Dream mode** — weekly/monthly pattern discovery across sessions
- **Reasoning trails** — track hypothesis chains for debugging complex problems
- **Corrections** — learn from mistakes, surface relevant ones before repeating
- **Goal tracking** — persistent goals with staleness detection
- **Business intelligence** — idea scoring, competitor tracking, pitch analytics
- **Session handoff** — structured carry-forward between sessions
- **Self-awareness** — reflection, blind spots, relationship pulse, growth intentions
- **34 MCP tools** across 11 modules

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

**[Full tool reference →](https://elara.navigatorbuilds.com/tools.html)**

## Prerequisites

- **Python 3.10+** — [Download here](https://www.python.org/downloads/)
- **Git** — [Download here](https://git-scm.com/downloads)

> **Windows users:** When installing Python, check **"Add python.exe to PATH"** at the bottom of the installer. This is unchecked by default and without it `pip` and `python` commands won't work.
>
> If Python is already installed but `pip` isn't recognized, try `python -m pip` instead of `pip`, or `py -m pip` on Windows.

## Quick Start

### Linux / macOS

```bash
pip install git+https://github.com/aivelikivodja-bot/elara-core.git
elara init
claude mcp add elara -- elara serve
```

### Windows (Command Prompt or PowerShell)

```
py -m pip install git+https://github.com/aivelikivodja-bot/elara-core.git
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

## Architecture

```
core/           Main orchestrator + central paths
daemon/         State, mood, presence, dreams, reasoning, corrections
memory/         ChromaDB vector memory, conversations, episodes
elara_mcp/      MCP server + 34 tool definitions
hooks/          Claude Code session hooks
interface/      Web dashboard (optional)
voice/          TTS via Piper (optional)
senses/         System monitoring (optional)
```

Key patterns:
- **Mixin composition** for large modules (Overwatch, ConversationMemory, EpisodicMemory)
- **Singleton pattern** via `get_*()` functions for memory systems
- **Pydantic schemas** for data validation
- **Atomic writes** to prevent corruption
- **Central paths module** (`core/paths.py`) — single source of truth for all file locations

## Development

```bash
# Clone and install in dev mode
git clone https://github.com/AiVelikIVodja/elara-core.git
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
