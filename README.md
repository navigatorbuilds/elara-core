# Elara Core

> **Layer 3 of the Elara Protocol — persistent memory, cognition, and awareness for AI systems.**

[![Tests](https://github.com/navigatorbuilds/elara-core/actions/workflows/tests.yml/badge.svg)](https://github.com/navigatorbuilds/elara-core/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/elara-core?color=%2300ff41&label=PyPI)](https://pypi.org/project/elara-core/)
[![Python](https://img.shields.io/pypi/pyversions/elara-core?color=%2300e5ff)](https://pypi.org/project/elara-core/)
[![License](https://img.shields.io/badge/license-BSL--1.1-ff0040)](https://github.com/navigatorbuilds/elara-core/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-elara.navigatorbuilds.com-%23ffb000)](https://elara.navigatorbuilds.com)

This is **one layer** of the [Elara Protocol](https://github.com/navigatorbuilds/elara-protocol) — a post-quantum universal validation layer for digital work. The full stack spans cryptographic signing, a Rust VM, decentralized network consensus, and this cognitive layer.

### Install in one line

```bash
# Linux / macOS
curl -sSL https://raw.githubusercontent.com/navigatorbuilds/elara-core/main/scripts/install.sh | sh

# Windows (PowerShell)
irm https://raw.githubusercontent.com/navigatorbuilds/elara-core/main/scripts/install.ps1 | iex

# Or with pip / pipx
pip install elara-core[network]
```

**Every install is a node.** When you run `elara serve`, your instance joins the Elara mesh network as a LEAF node — sharing anonymized validation records with other nodes. No personal data leaves your machine. Opt out anytime with `elara serve --no-node` or `elara node stop`.

```
The Elara Protocol Stack:
Layer 1   — Post-quantum cryptography (Dilithium3 + SPHINCS+), DAG signing, offline validation
Layer 1.5 — Rust DAM Virtual Machine (PyO3 bindings, record processing)
Layer 2   — Decentralized network (Adaptive Witness Consensus, peer discovery, trust scoring)
Layer 3   — AI cognition (THIS REPO) — memory, mood, reasoning, awareness
```

```
Network Topology:

  ┌──────┐     ┌──────┐     ┌──────┐
  │ LEAF │────▶│RELAY │◀────│ LEAF │    LEAF    = your install
  └──┬───┘     └──┬───┘     └──┬───┘    RELAY   = seed/routing node
     │            │            │         WITNESS = attestation authority
     ▼            ▼            ▼
  ┌──────────────────────────────┐
  │         WITNESS NODES         │
  │   Cross-sign validation       │
  │   records across the mesh     │
  └──────────────────────────────┘
```

**46 tools. 17 modules. 39K+ lines of Python. 240 tests. v0.17.0. Everything runs locally.** Cognitive outputs are dual-signed and stored in the cryptographic DAG. Pattern recognition feeds back into the validation chain.

```
You: "Morning."
Elara: "You were debugging the auth module at 2am. Did you sleep?"

You: "What happened this week?"
Elara: "3 work sessions. Auth module shipped. Goal #4 is stalling —
       no progress in 9 days. My overnight brain built 2 new models
       and flagged a prediction deadline in 3 days."
```

---

## Project Status

**This project is in active development.** The protocol layers are being built and integrated. Here's where things stand:

| Layer | Status | Repository |
|-------|--------|------------|
| **Layer 1** — Post-quantum crypto | Done | Private (pre-release) |
| **Layer 1.5** — Rust DAM VM | Done | [elara-runtime](https://github.com/navigatorbuilds/elara-runtime) |
| **Layer 2** — Network consensus | Active (node-by-default) | Included in this repo (`network/`) |
| **Layer 3** — AI cognition | Done | This repo |
| **Protocol specs** | v0.5.3 | [elara-protocol](https://github.com/navigatorbuilds/elara-protocol) |
| **US Provisional Patent** | Filed | Application No. 63/983,064 (Feb 14, 2026) |

Every install is a node. When you run `elara serve`, your instance participates in the decentralized mesh — sharing anonymized validation records, not personal data. The install scripts handle everything in one line.

---

## What This Repo Contains

Elara Core is the cognitive layer (Layer 3). It provides persistent intelligence for AI assistants via [Model Context Protocol (MCP)](https://modelcontextprotocol.io):

### Core

| Feature | What it does |
|---------|-------------|
| **Semantic memory** | Store and search by meaning, not keywords. "What were we doing last week?" just works. |
| **Long-range memory** | Temporal sweep across time windows at boot — surfaces important items from weeks or months ago, plus landmark memories that never fade. |
| **Mood system** | Tracks valence, energy, openness. Decays naturally between sessions. |
| **Session tracking** | Episodes with milestones, decisions, project tagging, and timeline view. |
| **Goals & corrections** | Persistent goals with staleness detection. Mistakes saved and surfaced before you repeat them. |
| **Decision registry** | SQLite-backed ledger of permanent verdicts (UDR). Crystallized decisions auto-fed from corrections and outcomes. O(1) hook injection prevents repeating failed actions. |
| **Session handoff** | Structured carry-forward between sessions so nothing gets lost. |

### Advanced

| Feature | What it does |
|---------|-------------|
| **3D Cognition** | Persistent models (understanding), predictions (foresight), principles (wisdom), and workflow patterns (action) that accumulate over time. |
| **Workflow Patterns** | Learned action sequences from episode history, proactively surfaced when a known trigger is detected mid-session. |
| **Knowledge Graph** | Document cross-referencing with 6-tuple addressing, SQLite + ChromaDB, 4 validators for contradiction detection. |
| **Cortical execution** | 5-layer concurrent architecture (Reflex → Reactive → Deliberative → Contemplative → Social). Hot cache, async event bus, worker pools — concurrent tool calls don't block each other. |
| **Overnight thinking** | Autonomous analysis between sessions — runs 15 phases through a local LLM, builds cognitive models, detects workflow patterns, makes predictions. |
| **Creative drift** | The overnight brain's imagination — random context collisions at high temperature. Writes to an accumulating creative journal. |
| **Dream mode** | Weekly/monthly pattern discovery across sessions, inspired by sleep consolidation. |
| **Reasoning trails** | Track hypothesis chains when debugging. Includes what was abandoned and why. |
| **Self-reflection** | Mood trends, blind spots, growth intentions. |
| **Layer 1 bridge** | Cognitive artifacts are dual-signed (Dilithium3 + SPHINCS+) and stored in the cryptographic DAG. |
| **Layer 2 network** | Peer discovery (mDNS), record exchange, witness attestation, weighted trust scoring. |
| **Tier system** | 4 hardware deployment levels (VALIDATE/REMEMBER/THINK/CONNECT) controlling which modules load at runtime. Runs on anything from IoT sensors to GPU servers. |
| **Cognitive continuity** | Hash-chained, dual-signed (Dilithium3 + SPHINCS+) cognitive state snapshots in the DAG. Cryptographic proof of unbroken AI experience. |

> **Note:** Overnight thinking requires [Ollama](https://ollama.ai) with a local LLM. Layer 1 bridge requires [elara-protocol](https://github.com/navigatorbuilds/elara-protocol). Layer 2 network requires `elara-core[network]`.

---

## Tools (46)

**Start here** (5 essential tools):

| Tool | What it does |
|------|-------------|
| `elara_remember` | Save something to memory |
| `elara_recall` | Search memories by meaning |
| `elara_mood` | Check emotional state |
| `elara_episode_start` | Begin tracking a work session |
| `elara_status` | Full status check |

<details>
<summary>All 46 tools by module</summary>

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
| **Workflows** | `elara_workflow` | 1 |
| **UDR** | `elara_udr` (record/check/scan/list/review/stats/boot/backfill) | 1 |
| **Knowledge** | `elara_kg_index`, `elara_kg_query`, `elara_kg_validate`, `elara_kg_diff` | 4 |
| **Business** | `elara_business` | 1 |
| **LLM** | `elara_llm` | 1 |
| **Gmail** | `elara_gmail` | 1 |
| **Maintenance** | `elara_rebuild_indexes`, `elara_briefing`, `elara_snapshot`, `elara_memory_consolidation` | 4 |
| **Network** | `elara_network` | 1 |

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
│              hooks/ (hippocampus)                  │
│                                                  │
│  Intention resolver · Rolling message buffer     │
│  Semantic recall · Compound queries · Dedup      │
│  Frustration detection · Context injection       │
│  Long-range temporal sweep · Landmark recall     │
├──────────────────────────────────────────────────┤
│              Cortical Execution Model             │
│                                                  │
│  L0 REFLEX     — Hot cache, instant reads        │
│  L1 REACTIVE   — Async event bus, cascading fx   │
│  L2 DELIBERATE — IO pool (4) + LLM pool (2)     │
│  L3 CONTEMPLATE — Overnight brain, dreams        │
│  L4 SOCIAL     — Peer network, witness consensus │
├──────────────────────────────────────────────────┤
│              elara_mcp/tools/ (46 tools)          │
│                                                  │
│  Memory · Mood · Episodes · Goals · Awareness    │
│  Dreams · Cognitive · 3D Cognition · Workflows   │
│  UDR · Knowledge · Business · LLM · Gmail        │
│  Maintenance · Network                            │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              daemon/ + core/                      │
│                                                  │
│  State engine · Emotions · Models · Predictions  │
│  Principles · Workflows · Overnight brain · Drift│
└────────┬───────────────────────┬────────────────┘
         │                       │
┌────────▼────────┐    ┌────────▼────────────────┐
│   ~/.elara/      │    │   Layer 1 Bridge        │
│   (all local)    │    │   Dilithium3 + SPHINCS+ │
│                  │    │   DAG signing            │
│  ChromaDB (14)   │    │   → Layer 2 Network     │
│  JSON state      │    │   → Witness consensus   │
│  Overnight data  │    │   → Trust scoring       │
└─────────────────┘    └─────────────────────────┘
```

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

### CLI commands

```
elara init                     Interactive setup wizard
elara init --yes               Non-interactive init (CI/scripts)
elara doctor                   Diagnostic health check
elara serve                    Start MCP server + network node (stdio)
elara serve --no-node          Start MCP server without network
elara serve --profile full     Start with all 46 tool schemas
elara node status              Show node info (type, port, peers)
elara node peers               List connected peers
elara node stop                Disable network node
elara node start               Enable network node
elara sign <file>              Sign a file with Layer 1 crypto
elara verify <proof>           Verify an .elara.proof file
elara identity                 Show identity info
elara dag stats                Show DAG statistics
elara serve --tier {0,1,2,3}   Set hardware deployment tier
elara continuity status        Show cognitive continuity chain info
elara continuity verify        Verify chain integrity
elara testnet                  Run Layer 2 testnet demo
elara --version                Show version
```

---

## Compatibility

| | Supported |
|---|---|
| **Python** | 3.10, 3.11, 3.12 |
| **OS** | Linux, macOS, Windows (WSL recommended) |
| **MCP Clients** | Claude Code, Claude Desktop, Cursor, Windsurf, Cline |

---

## The Elara Protocol

The [Elara Protocol](https://github.com/navigatorbuilds/elara-protocol) is a post-quantum universal validation layer for digital work — from a poem written on a $30 phone in Kenya to telemetry from a Mars colony. It introduces the **Directed Acyclic Mesh (DAM)**, a novel 5-dimensional data structure with partition-tolerant consensus across planetary distances.

| Document | Where |
|----------|-------|
| **Elara Protocol Whitepaper v0.5.3** | [GitHub](https://github.com/navigatorbuilds/elara-protocol) |
| **Elara Core Whitepaper v1.5.1** | [GitHub](https://github.com/navigatorbuilds/elara-protocol) |
| **US Provisional Patent** | Application No. 63/983,064 (Feb 14, 2026) |

**What Layer 3 adds to the protocol:**
- Cognitive outputs (predictions, models, principles) are dual-signed with Dilithium3 + SPHINCS+ and stored in the cryptographic DAG via the Layer 1 bridge
- Pattern recognition across validation streams — anomaly detection, fraud prediction, routing optimization
- Continuous autonomous thinking — 15-phase analysis engine running every 2 hours
- Dual-use architecture: industrial applications (manufacturing, research) and emotional companionship (humanoid robotics, therapeutic AI) from a single codebase

---

## What's New

**v0.17.0 — Awareness Engine v2** — Complete rewrite of session boot injection. New sessions use chronological recall instead of semantic search, fixing the "broken record" problem. Dedicated boot path with last-session summary, recent work, and next concrete action. Carry-forward decay suppresses stale items after 14 sessions. Staleness filters for intentions and context. 46 tools across 17 modules. 240 tests.

**v0.16.0 — Unified Decision Registry (UDR)** — SQLite-backed decision ledger that crystallizes permanent verdicts from corrections and outcomes. In-memory Python set for O(1) hook checks — zero LLM overhead. Auto-feeds from corrections (mistakes) and outcomes (losses). New `elara_udr` tool with 8 actions. Intention hook now injects `[DECISION-CHECK]` warnings before you repeat failed actions. 46 tools across 17 modules. 240 tests.

**v0.15.0 — Tier System + Cognitive Continuity Chain** — 4 hardware deployment tiers (VALIDATE/REMEMBER/THINK/CONNECT) so Elara runs on anything from a $30 phone to a satellite. Cognitive Continuity Chain: hash-chained, dual-signed state snapshots in the DAG — cryptographic proof of unbroken AI experience. `elara serve --tier`, `elara continuity status/verify`.

**v0.14.0 — One-Line Install + Every Install Is a Node** — One-line install scripts for Linux, macOS, and Windows. `elara serve` now automatically starts a LEAF network node (opt out with `--no-node`). New `elara node` subcommand for node management. Seed node bootstrap with GitHub peer list fallback. PyPI version check on startup. `elara --version` flag.

**v0.13.0 — Cortical Execution Model + Long-Range Memory** — 5-layer concurrent architecture: hot cache (L0), async event bus (L1), worker pools (L2), brain events (L3), network consolidation (L4). All 45 tool handlers are now non-blocking. Plus temporal sweep at boot — surfaces important memories from weeks/months ago and landmark memories that never fade. Timeline view for milestones.

**v0.12.0 — Testnet Hardening** — Witness signature verification (Dilithium3), peer rate limiting, attestation back-propagation, heartbeat protocol, weighted trust with temporal decay + diversity bonus, role enforcement.

**v0.11.0 — Layer 2 Network + CLI Tools** — Minimum viable network: mDNS peer discovery, HTTP record exchange, witness attestation, trust scoring. CLI: `elara sign/verify/identity/dag`. Bridge hardened with validation guards, dedup (10K cache), and rate limiting (120/min).

**v0.10.8 — Layer 1 Bridge** — Cryptographic validation of cognitive artifacts. Predictions, corrections, models, principles, and other significant events are dual-signed (Dilithium3 + SPHINCS+) and stored in a local DAG.

**v0.10.7 — Workflow Patterns** — Learned action sequences from episode history. The overnight brain detects recurring multi-step processes and crystallizes them into workflow patterns.

**v0.10.6 — Knowledge Graph** — Document cross-referencing with 6-tuple addressing. SQLite + ChromaDB backend. 4 validators for contradiction detection.

**v0.10.0 — 3D Cognition** — Persistent models (understanding), predictions (foresight), and principles (wisdom) that accumulate over time. Plus creative drift — the overnight brain's imagination.

**[Full changelog →](CHANGELOG.md)**

---

## Community

- **[Docs](https://elara.navigatorbuilds.com)** — Architecture, tool reference, persona templates
- **[Discussions](https://github.com/navigatorbuilds/elara-core/discussions)** — Questions, ideas, showcase
- **[Issues](https://github.com/navigatorbuilds/elara-core/issues)** — Bug reports and feature requests
- **[Contributing](CONTRIBUTING.md)** — How to help

---

If Elara resonates with you, a star helps others find it. ⭐
