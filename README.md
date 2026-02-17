# Elara Core

> **Your AI doesn't remember yesterday. Elara fixes that.**

[![Tests](https://github.com/navigatorbuilds/elara-core/actions/workflows/tests.yml/badge.svg)](https://github.com/navigatorbuilds/elara-core/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/elara-core?color=%2300ff41&label=PyPI)](https://pypi.org/project/elara-core/)
[![Python](https://img.shields.io/pypi/pyversions/elara-core?color=%2300e5ff)](https://pypi.org/project/elara-core/)
[![License](https://img.shields.io/badge/license-BSL--1.1-ff0040)](https://github.com/navigatorbuilds/elara-core/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-elara.navigatorbuilds.com-%23ffb000)](https://elara.navigatorbuilds.com)

Elara gives your AI assistant persistent memory, mood, self-awareness, and overnight thinking — all through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). **39 tools. 12 modules. 26K+ lines of Python. Everything runs locally.**

```
You: "Morning."
Elara: "You were debugging the auth module at 2am. Did you sleep?"

You: "What happened this week?"
Elara: "3 work sessions. Auth module shipped. Goal #4 is stalling —
       no progress in 9 days. My overnight brain built 2 new models
       and flagged a prediction deadline in 3 days."
```

---

## What is MCP?

[Model Context Protocol](https://modelcontextprotocol.io) is how AI assistants (Claude Code, Cursor, Windsurf, etc.) connect to external tools. Think of it as a USB port for AI — plug Elara in and your assistant gains memory, mood, and awareness. No code changes needed.

---

## Install (2 minutes)

### Prerequisites

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **An MCP client** — [Claude Code](https://claude.ai/code), [Cursor](https://cursor.sh), or any MCP-compatible editor

> **Windows users:** When installing Python, check **"Add python.exe to PATH"** at the bottom of the installer.

### Step 1: Install Elara

```bash
pip install elara-core
```

<details>
<summary>Windows? Use <code>py -m pip install elara-core</code></summary>

If `pip` isn't recognized, try:
```
py -m pip install elara-core
```
Or:
```
python -m pip install elara-core
```
</details>

### Step 2: Initialize

```bash
elara init
```

You should see:
```
Elara initialized at /home/yourname/.elara

Next steps:
  1. Add Elara to your MCP client:
     claude mcp add elara -- elara serve

  2. (Optional) Create a persona in your CLAUDE.md:
     See examples/CLAUDE.md.example for a template
```

This creates `~/.elara/` with default config files. All your data lives here.

### Step 3: Connect to your AI

**Claude Code:**
```bash
claude mcp add elara -- elara serve
```

**Cursor / Other MCP clients:**

Add this to your MCP config (usually `~/.cursor/mcp.json` or similar):
```json
{
  "mcpServers": {
    "elara": {
      "command": "elara",
      "args": ["serve"]
    }
  }
}
```

### Step 4: Verify it works

Open a new session in your AI client and say:

> "Use elara_status to check if Elara is running."

You should get back a status message with mood, presence, and memory counts. If you see that, **you're done**.

---

## First 5 Minutes

Once Elara is connected, try these in your AI session:

```
"Remember that I prefer dark themes and use pytest for testing."
→ Stored in semantic memory. Elara will recall this by meaning, not keywords.

"How am I doing?"
→ Returns mood state (valence, energy, openness).

"Start an episode — we're working on the auth module."
→ Begins tracking this work session with milestones and decisions.

"What do you remember about my preferences?"
→ Searches semantic memory and returns relevant matches.

"Set a goal: Ship auth module by Friday."
→ Tracked persistently. Elara will remind you if it stalls.
```

That's the core loop: **remember → recall → track → reflect**.

---

## What Elara Does

### Core (works out of the box)

| Feature | What it does |
|---------|-------------|
| **Semantic memory** | Store and search by meaning, not keywords. "What were we doing last week?" just works. |
| **Mood system** | Tracks valence, energy, openness. Decays naturally between sessions. |
| **Session tracking** | Episodes with milestones, decisions, and project tagging. |
| **Goals & corrections** | Persistent goals with staleness detection. Mistakes saved and surfaced before you repeat them. |
| **Session handoff** | Structured carry-forward between sessions so nothing gets lost. |

### Advanced

| Feature | What it does |
|---------|-------------|
| **3D Cognition** *(new in v0.10.0)* | Persistent models (understanding), predictions (foresight), and principles (wisdom) that accumulate over time. |
| **Overnight thinking** | Autonomous analysis between sessions — runs 14 phases through a local LLM, builds cognitive models, makes predictions. |
| **Creative drift** | The overnight brain's imagination — random context collisions at high temperature. Writes to an accumulating creative journal. |
| **Dream mode** | Weekly/monthly pattern discovery across sessions, inspired by sleep consolidation. |
| **Reasoning trails** | Track hypothesis chains when debugging. Includes what was abandoned and why. |
| **Self-reflection** | Mood trends, blind spots, growth intentions. |
| **RSS briefing** | External news feeds for context. |

> **Note:** Overnight thinking and creative drift require [Ollama](https://ollama.ai) with a local LLM (e.g., `qwen2.5:32b`). Everything else works without it.

---

## Tools Quick Reference

**Start here** (5 essential tools):

| Tool | What it does |
|------|-------------|
| `elara_remember` | Save something to memory |
| `elara_recall` | Search memories by meaning |
| `elara_mood` | Check emotional state |
| `elara_episode_start` | Begin tracking a work session |
| `elara_status` | Full status check |

**All 38 tools by module:**

<details>
<summary>Click to expand full tool list</summary>

| Module | Tools | Count |
|--------|-------|-------|
| **Memory** | `elara_remember`, `elara_recall`, `elara_recall_conversation`, `elara_conversations` | 4 |
| **Mood** | `elara_mood`, `elara_mood_adjust`, `elara_imprint`, `elara_mode`, `elara_status` | 5 |
| **Episodes** | `elara_episode_start`, `elara_episode_note`, `elara_episode_end`, `elara_episode_query`, `elara_context` | 5 |
| **Goals** | `elara_goal`, `elara_goal_boot`, `elara_correction`, `elara_correction_boot`, `elara_handoff` | 5 |
| **Awareness** | `elara_reflect`, `elara_insight`, `elara_intention`, `elara_observe`, `elara_temperament` | 5 |
| **Dreams** | `elara_dream`, `elara_dream_info` | 2 |
| **Cognitive** | `elara_reasoning`, `elara_outcome`, `elara_synthesis` | 3 |
| **3D Cognition** | `elara_model`, `elara_prediction`, `elara_principle` | 3 |
| **Business** | `elara_business` | 1 |
| **LLM** | `elara_llm` | 1 |
| **Gmail** | `elara_gmail` | 1 |
| **Maintenance** | `elara_rebuild_indexes`, `elara_briefing`, `elara_snapshot` | 3 |

</details>

**[Full tool reference →](https://elara.navigatorbuilds.com/tools.html)**

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              YOUR MCP CLIENT                     │
│     Claude Code · Cursor · Windsurf · Cline      │
└────────────────────┬────────────────────────────┘
                     │ MCP Protocol (stdio)
┌────────────────────▼────────────────────────────┐
│              elara_mcp/tools/                     │
│                                                  │
│  Memory · Mood · Episodes · Goals · Awareness    │
│  Dreams · Cognitive · 3D Cognition · Business    │
│  LLM · Gmail · Maintenance                      │
│                  (38 tools)                       │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              daemon/ + core/                      │
│                                                  │
│  State engine · Emotions · Models · Predictions  │
│  Principles · Dreams · Overnight brain · Drift   │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           ~/.elara/ (all local)                   │
│                                                  │
│  ChromaDB (7 collections) · JSON state files     │
│  Overnight findings · Creative journal           │
└─────────────────────────────────────────────────┘
```

---

## Configuration

### Data directory

Default: `~/.elara/`. Override with:

```bash
export ELARA_DATA_DIR=/your/custom/path
# or
elara serve --data-dir /your/custom/path
```

### Persona

Elara's personality comes from your AI client's system prompt (e.g., `CLAUDE.md`), not from the code. Copy the included template to get started:

```bash
cp examples/CLAUDE.md.example ~/.claude/CLAUDE.md
```

Edit it to make Elara yours — name, personality, boot behavior, session-end behavior.

### Overnight thinking (optional)

Requires [Ollama](https://ollama.ai) with a model installed:

```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull qwen2.5:32b

# Run overnight thinking manually
cd /path/to/elara-core
python3 -m daemon.overnight --mode exploratory
```

---

## Troubleshooting

**"elara: command not found"**
→ Your Python scripts directory isn't in PATH. Try: `python -m elara_mcp.cli serve`

**"No module named 'chromadb'"**
→ Reinstall: `pip install elara-core --force-reinstall`

**MCP client doesn't see Elara tools**
→ Make sure you restarted your client after adding the MCP config. Check with: `claude mcp list`

**"Elara initialized" but tools don't work**
→ Run `elara serve` in a terminal to see error output. Most common: Python version too old (need 3.10+).

---

## Development

```bash
git clone https://github.com/navigatorbuilds/elara-core.git
cd elara-core
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

---

## Compatibility

| | Supported |
|---|---|
| **Python** | 3.10, 3.11, 3.12 |
| **OS** | Linux, macOS, Windows (WSL recommended) |
| **MCP Clients** | Claude Code, Claude Desktop, Cursor, Windsurf, Cline |

---

## Whitepapers & Protocol

Elara Core is the **Layer 3 reference implementation** of the [Elara Protocol](https://github.com/navigatorbuilds/elara-protocol) — a post-quantum universal validation layer for digital work.

| Document | Description |
|----------|-------------|
| [**Elara Core Whitepaper v1.3.1**](ELARA-CORE-WHITEPAPER.v1.3.1.md) | Full architecture: 3D Cognition, persistent memory, emotional modeling, deployment modularity, continuous autonomous thinking |
| [**Elara Protocol**](https://github.com/navigatorbuilds/elara-protocol) | The universal validation protocol — DAM architecture, post-quantum crypto, interplanetary operations |

**Dual-use architecture:** Elara Core serves both industrial applications (manufacturing monitoring, research assistants, anomaly detection) and emotional companionship systems (humanoid robotics, therapeutic AI, personal companions) from a single codebase. See [Whitepaper Section 2.3](ELARA-CORE-WHITEPAPER.v1.3.1.md#23-deployment-modularity-two-independent-axes).

---

## Community

- **[Docs](https://elara.navigatorbuilds.com)** — Quickstart, tool reference, architecture, persona templates
- **[Discussions](https://github.com/navigatorbuilds/elara-core/discussions)** — Questions, ideas, showcase
- **[Issues](https://github.com/navigatorbuilds/elara-core/issues)** — Bug reports and feature requests
- **[Contributing](CONTRIBUTING.md)** — How to help

---

## What's New in v0.10.0

**3D Cognition System** — Elara now builds persistent understanding between sessions:
- **Cognitive Models** — understanding that accumulates evidence and adjusts confidence over time
- **Predictions** — explicit forecasts with deadlines and accuracy tracking
- **Principles** — crystallized rules from repeated insights

**Creative Drift** — the overnight brain's imagination. Random context collisions at high temperature, writing to an accumulating creative journal.

**[Full changelog →](CHANGELOG.md)**

---

If Elara resonates with you, a star helps others find it. ⭐
