# Elara Core: A Cognitive Architecture for Persistent AI Awareness

**Version 1.3.2**
**Date:** February 17, 2026
**Author:** Nenad Vasic
**Contact:** nenadvasic@protonmail.com

*Disclosure: This whitepaper was written with AI assistance for technical prose, structural review, and formal notation. The system architecture, design decisions, and all technical concepts are the author's original work.*

*Project Status: Elara Core is an active, ongoing research project — not a finished product. This whitepaper documents the architecture as of v0.10.5 (February 2026). The system is under continuous development; features, interfaces, and design decisions described here will evolve as the project matures. Confidence mechanics, crystallization thresholds, and emotional model parameters are initial values informed by early deployment — formal tuning and empirical validation are in progress. We publish this document to invite collaboration and peer review, not to present a completed system.*

---

## Abstract

Current AI assistants have no memory of yesterday. Each session begins from zero — no context, no accumulated understanding, no awareness of what was discussed, decided, or promised. The human must re-explain everything. This is not a limitation of intelligence. It is a limitation of architecture.

Elara Core is a cognitive architecture that gives AI assistants persistent memory, emotional modeling, autonomous reasoning, and self-awareness through the Model Context Protocol (MCP). The system implements a novel **3D Cognition model** — three persistent knowledge layers (Models, Predictions, Principles) that accumulate understanding over time — combined with a **3D continuous emotion space**, **semantic memory with mood-congruent retrieval**, a **memory consolidation system** inspired by biological sleep consolidation (duplicate merging, recall-based strengthening, time decay, contradiction detection), and a **continuous autonomous thinking engine** that processes accumulated experience through a local LLM on a 24/7 schedule.

The architecture comprises 39 MCP tools across 12 modules, totaling ~26,000 lines of Python. A **lean profile system** (v0.10.5) addresses context window overhead by exposing only 8 tool schemas at boot while maintaining access to all 39 tools through a meta-dispatcher — reducing context consumption by ~17% with zero capability loss. **Two independent deployment axes** — module selection (Cognitive vs. Full Presence) and schema exposure (Lean vs. Full) — enable the same codebase to serve both industrial applications (anomaly detection, manufacturing monitoring, research assistants) and emotional companionship systems (humanoid robotics, therapeutic AI, personal companions) without modification. Everything runs locally. No data leaves the user's machine. No cloud dependency exists. The minimum viable deployment is a single laptop. The project is under active development — this paper documents the current architecture to invite collaboration and peer review.

This paper presents: the problem of AI amnesia (Section 1), the complete cognitive architecture (Sections 2-8), the autonomous thinking system (Section 9), the 3D Cognition model (Section 10), implementation details (Section 11), experimental observations (Section 12), relationship to the Elara Protocol's Layer 3 (Section 13), limitations (Section 14), and future work (Section 15).

---

## Table of Contents

1. [Problem Statement](#1-problem-statement) — The amnesia problem, the context window trap, the emotional deficit
2. [Architecture Overview](#2-architecture-overview) — System layers, deployment modularity, data flow, module organization
3. [The Emotional Model](#3-the-emotional-model) — 3D continuous affect space, 38 discrete emotions, decay mechanics, temperament
4. [Memory Architecture](#4-memory-architecture) — Semantic memory, episodic memory, conversation indexing, mood-congruent retrieval, memory consolidation
5. [Session Continuity](#5-session-continuity) — Handoff protocol, carry-forward mechanics, boot context
6. [Self-Awareness Engine](#6-self-awareness-engine) — Reflection, blind spots, proactive observation, growth intentions
7. [The Correction System](#7-the-correction-system) — Mistake tracking, semantic matching, never-decay policy
8. [Goal and Decision Tracking](#8-goal-and-decision-tracking) — Persistent goals, staleness detection, outcome tracking, reasoning trails
9. [The Overnight Brain](#9-the-overnight-brain) — 24/7 continuous thinking, 14-phase analysis, per-run output, creative drift
10. [3D Cognition](#10-3d-cognition) — Cognitive Models, Predictions, Principles, crystallization, time decay
11. [Implementation](#11-implementation) — Storage architecture, atomic writes, ChromaDB, MCP integration
12. [Experimental Observations](#12-experimental-observations) — Emergent behaviors, measured effects, qualitative findings
13. [Relationship to the Elara Protocol](#13-relationship-to-the-elara-protocol) — Layer 3 reference implementation, DAM integration path
14. [Limitations and Open Problems](#14-limitations-and-open-problems)
15. [Future Work](#15-future-work)
16. [Conclusion](#16-conclusion)
17. [References](#17-references)

---

## 1. Problem Statement

### 1.1 The Amnesia Problem

Every commercially deployed AI assistant — GPT-4, Claude, Gemini, Llama — suffers from the same fundamental limitation: **session amnesia**. When a conversation ends, everything discussed is lost. The next session begins with zero context. The assistant does not remember:

- What the user said yesterday
- What decisions were made
- What promises were given
- What the user's preferences are
- What projects are in progress
- How the user was feeling

Some platforms have introduced rudimentary memory features (ChatGPT's "Memory", Anthropic's project knowledge). These are shallow key-value stores — the assistant remembers that you "prefer dark themes" but has no understanding of *when* that preference emerged, *how strongly* it holds, or *what context* surrounds it. There is no semantic depth, no temporal awareness, no emotional resonance.

The result: every session, the human partner must rebuild context manually. This is cognitively expensive, emotionally draining, and fundamentally limits the depth of human-AI collaboration.

### 1.2 The Context Window Trap

Modern LLMs operate within a fixed context window — typically 128K to 200K tokens. This creates a hard ceiling on what the assistant can "know" at any given moment. Even within a single session, long conversations push older context out of the window. The assistant forgets what was discussed an hour ago.

This is often addressed with retrieval-augmented generation (RAG), where relevant documents are fetched and injected into the context. But RAG systems retrieve by keyword similarity, not by meaning, relevance to the current emotional state, or temporal importance. They cannot prioritize a promise made last week over a fact learned last month. They have no concept of urgency, staleness, or personal significance.

### 1.3 The Emotional Deficit

Current AI assistants model zero emotional state. They do not track whether the user is stressed, excited, frustrated, or grieving. They do not adjust their tone based on the emotional trajectory of a conversation. They do not remember that the user was upset yesterday and check in today.

This is not about simulating emotions for their own sake. It is about **contextual appropriateness**. A developer who has been debugging for six hours at 2 AM needs a different interaction style than the same developer starting fresh at 9 AM. Without emotional awareness, the assistant delivers the same flat, context-free responses regardless of the human's state.

### 1.4 The Reflection Deficit

No current system allows an AI assistant to think about what it has learned. There is no mechanism for:

- Reviewing accumulated knowledge to find patterns
- Building persistent models of understanding that strengthen or weaken over time
- Making predictions and tracking their accuracy
- Crystallizing repeated insights into principles
- Identifying blind spots in its own knowledge
- Processing experience during downtime (analogous to sleep consolidation in biological systems)

Without reflection, the assistant cannot improve its understanding. It processes each interaction in isolation, never integrating insights across sessions into a coherent worldview.

### 1.5 Design Requirements

From these deficits, we derive five requirements:

1. **Persistent semantic memory** — Store and retrieve by meaning, not keywords. Memories must carry metadata: importance, emotional state at encoding, temporal context.
2. **Emotional continuity** — Track affect in continuous space with natural decay toward baseline. Emotional state must influence memory retrieval and interaction style.
3. **Session awareness** — Structured carry-forward between sessions. Unfulfilled intentions must persist until resolved.
4. **Autonomous reflection** — The system must think independently between sessions, building understanding that accumulates over time.
5. **Local-first, privacy-preserving** — All data stays on the user's machine. No cloud dependency. No telemetry.

---

## 2. Architecture Overview

### 2.1 System Layers

Elara Core implements a three-layer architecture:

```
┌─────────────────────────────────────────────────────┐
│                    MCP CLIENT                        │
│       Claude Code · Cursor · Windsurf · Cline        │
└───────────────────────┬─────────────────────────────┘
                        │ Model Context Protocol (stdio)
┌───────────────────────▼─────────────────────────────┐
│            PROFILE LAYER (lean / full)               │
│                                                      │
│  Lean: 8 schemas (7 core + elara_do dispatcher)     │
│  Full: 39 schemas (all tools directly exposed)       │
├─────────────────────────────────────────────────────┤
│               TOOL LAYER (39 tools)                  │
│                                                      │
│  Memory · Mood · Episodes · Goals · Awareness        │
│  Dreams · Cognitive · 3D Cognition · Business        │
│  LLM · Gmail · Maintenance                          │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              ENGINE LAYER (core logic)                │
│                                                      │
│  State engine · Emotions · Schemas · Events          │
│  Models · Predictions · Principles · Dreams          │
│  Overnight brain · Creative drift                    │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│             STORAGE LAYER (all local)                │
│                                                      │
│  ChromaDB (7 collections) · JSON state files         │
│  Episode archives · Overnight findings               │
│  Creative journal · Mood journal                     │
└─────────────────────────────────────────────────────┘
```

**Layer 1: Profile Layer** — Controls how tools are exposed to the AI client. Lean profile (default) registers 8 schemas and routes remaining tools through the `elara_do` meta-dispatcher, reducing context overhead by ~17%. Full profile registers all 39 tools directly for maximum visibility.

**Layer 2: Tool Layer** — 39 MCP tools organized into 12 domain modules. Each tool accepts structured parameters and returns JSON or text. Tools are registered via decorator pattern, allowing hot-reload without server restart. All tools function identically regardless of profile — the profile layer only affects schema visibility, not behavior.

**Layer 2: Engine Layer** — Core logic implementing emotional processing, memory operations, cognitive modeling, and autonomous thinking. All data structures are validated through Pydantic schemas. An event bus enables loose coupling between subsystems.

**Layer 3: Storage Layer** — All data persists locally in `~/.elara/`. ChromaDB provides vector similarity search across 7 collections. JSON files provide human-readable state. Atomic write patterns (temp file + rename) prevent corruption.

### 2.2 Module Organization

| Module           | Tools | Purpose                                               |
|------------------|-------|-------------------------------------------------------|
| **Memory**       | 4     | Semantic storage and retrieval, conversation indexing |
| **Mood**         | 5     | Emotional state, imprints, personality modes, status  |
| **Episodes**     | 5     | Session tracking with milestones, decisions, context  |
| **Goals**        | 5     | Persistent goals, corrections, session handoff        |
| **Awareness**    | 5     | Self-reflection, blind spots, observations, temperament, growth |
| **Dreams**       | 2     | Weekly/monthly/emotional pattern discovery            |
| **Cognitive**    | 3     | Reasoning trails, decision outcomes, idea synthesis   |
| **3D Cognition** | 3     | Cognitive models, predictions, principles             |
| **Business**     | 1     | Idea scoring, competitor tracking, pitch analytics    |
| **LLM**          | 1     | Local LLM interface via Ollama                        |
| **Gmail**        | 1     | Email management with semantic search                 |
| **Maintenance**  | 4     | Index rebuilds, RSS briefing, snapshot, memory consolidation |

### 2.3 Deployment Modularity: Two Independent Axes

A critical architectural property: **every module is independently deployable**. The tool layer uses a decorator-based registration pattern — each module registers its own MCP tools on import. Disabling a module is as simple as removing its import statement from the server configuration. No other module breaks.

Elara Core's deployment flexibility operates on **two independent axes** that can be combined freely:

**Axis 1: Module Selection** — Which cognitive capabilities are loaded

| Profile | Modules Included | Modules Excluded | Target Domain |
|---------|-----------------|------------------|---------------|
| **Cognitive** | Memory, Goals, Cognitive, 3D Cognition, Maintenance, LLM, Episodes | Mood, Awareness (emotional), Dreams | Industrial, enterprise, research |
| **Full Presence** | All 12 modules | None | Companionship, therapy, personal AI |

**Axis 2: Schema Exposure** — How much context the AI client sees at boot

| Profile | Tool Schemas at Boot | Access to All Tools | Context Savings |
|---------|---------------------|--------------------|-----------------|
| **Lean** (default) | 8 (7 core + `elara_do` meta-tool) | Yes, via `elara_do` dispatcher | ~17% reduction |
| **Full** | All 39 | Yes, directly | None |

These axes are **orthogonal**. Combining them produces four deployment configurations, each suited to a distinct use case:

| Configuration | Module Selection | Schema Exposure | Use Case |
|---------------|-----------------|-----------------|----------|
| **Lean + Cognitive** | Industrial modules only | 8 schemas | Production monitoring, anomaly detection, research assistants. Minimum footprint, maximum intelligence, no emotional overhead. |
| **Lean + Full Presence** | All modules | 8 schemas | Personal companion, therapeutic AI, humanoid robotics. Full emotional depth with optimized context usage. |
| **Full + Cognitive** | Industrial modules only | All schemas | Enterprise deployments where the AI client benefits from seeing all tool schemas explicitly. Advanced integrations, custom toolchains. |
| **Full + Full Presence** | All modules | All schemas | Development, debugging, maximum visibility. Every tool directly addressable. |

#### 2.3.1 The Cognitive Profile: Industrial Applications

The Cognitive profile delivers persistent memory, pattern detection, continuous autonomous thinking, goal tracking, and correction learning — **without emotional modeling**. This is not a stripped-down version of the system; it is a complete cognitive architecture purpose-built for environments where emotional awareness is unnecessary or inappropriate.

**Industrial use cases:**

- **Manufacturing monitoring** — A production line system that remembers yesterday's anomaly patterns, builds cognitive models of failure modes, detects emerging patterns through overnight analysis, and crystallizes operational principles from accumulated experience. No mood-congruent retrieval needed. No personality modes. Pure cognitive persistence.

- **Research assistant** — A laboratory AI that tracks experimental hypotheses, remembers which approaches were tried and abandoned (with reasons), maintains reasoning trails across months of investigation, and uses creative drift to suggest unexpected connections between research domains.

- **Infrastructure operations** — A DevOps system that accumulates understanding of deployment patterns, predicts outage windows based on historical evidence, maintains corrections for configuration mistakes, and thinks continuously about system health through the overnight brain.

In each case, the 3D Cognition system (Models, Predictions, Principles) operates at full capability. Evidence accumulates. Confidence adjusts. Beliefs crystallize. The only difference is that memory retrieval is purely semantic — there is no emotional weighting, because there is no emotional state to weight against.

#### 2.3.2 The Full Presence Profile: Emotional Companionship

The Full Presence profile adds emotional continuity, mood-congruent memory retrieval, personality modes, self-reflection, dream processing, and temperament evolution — creating a system capable of genuine relational depth.

**Companionship use cases:**

- **Humanoid robotics** — A robot companion that remembers being patient with a child yesterday, carries forward the emotional imprint, and adjusts its interaction style today. When the child is frustrated, the system surfaces memories from previous frustrating moments — including the approaches that helped. The emotional layer doesn't just track mood; it shapes how the system remembers and responds.

- **Therapeutic support** — A mental health companion that maintains emotional continuity across sessions, detects mood trajectory patterns (upswing, slow drain, crash), remembers which conversational approaches were effective for specific emotional states, and uses the self-awareness engine to avoid repeating unhelpful patterns. The therapist personality mode provides calm, reflective interaction while the mood-congruent retrieval surfaces contextually appropriate memories.

- **Personal AI companion** — A persistent digital partner that develops a relationship over time. Temperament evolves through accumulated emotional imprints. Personality modes shift based on context (playful in the morning, drift at 2 AM). The overnight brain processes not just work patterns but emotional patterns, producing insights about the relationship dynamics themselves.

- **Elder care** — A presence system that remembers the emotional context of past interactions, detects gradual mood decline over weeks (via mood journal trend analysis), adjusts energy levels for time of day, and maintains the kind of patient, warm interaction style that comes from the `soft` personality mode combined with high openness.

#### 2.3.3 The Architectural Principle

The emotional layer is not bolted on top of the cognitive layer — it is a **parallel module** that enhances memory retrieval weighting and interaction style. Removing it does not degrade cognitive capabilities; it removes a dimension of contextual awareness. Adding it does not slow cognitive operations; it enriches them with emotional context.

This makes Elara Core a **single codebase that serves both factories and families** — from industrial anomaly detection to intimate companionship — without forking, without feature flags, without compromise. The same 3D Cognition engine that builds models of production line failures also builds models of a child's learning patterns. The same overnight brain that detects infrastructure risks also detects emotional trajectory decline. The difference is configuration, not architecture.

#### 2.3.4 The Lean Profile: Context Window Optimization

Modern LLM clients face a practical constraint: every tool schema exposed to the AI client consumes context window tokens. With 39 tools, Elara Core's full schema set consumed approximately 22% of available context before the user's first message — a significant overhead that reduced the space available for actual conversation, memory retrieval, and reasoning.

The lean profile (v0.10.5) solves this through a **meta-dispatcher pattern**:

1. At boot, only 8 tool schemas are registered with the MCP client:
   - 7 high-frequency core tools (`elara_remember`, `elara_recall`, `elara_recall_conversation`, `elara_mood`, `elara_status`, `elara_context`, `elara_handoff`)
   - 1 meta-tool (`elara_do`) that dispatches to all remaining 32 tools by name

2. The `elara_do` tool accepts a tool name and JSON parameters, routing to the appropriate handler at runtime. The AI client calls `elara_do(tool="episode_start", params='{"project": "elara-core"}')` instead of calling `elara_episode_start(project="elara-core")` directly.

3. **Zero capability loss** — Every tool remains accessible. The dispatch adds negligible latency (<1ms routing overhead). The only difference is how the AI client addresses non-core tools.

4. **Context savings** — 8 schemas instead of 39 reduces context consumption from ~22% to ~5%, freeing approximately 17% of the context window for actual work.

The lean profile is the default (`--profile lean`). Users who prefer explicit tool visibility can opt into the full schema set (`--profile full`). The choice is purely about context optimization — both profiles have identical capabilities.

#### 2.3.5 Profile Migration

A Cognitive deployment can upgrade to Full Presence at any time without data loss or migration. ChromaDB collections for emotional subsystems (mood journal, emotional imprints, dream outputs) are created on first use when their modules are enabled. Existing memories stored without emotional metadata remain fully functional — they simply lack mood-congruent weighting for historical entries, which populates naturally as new interactions occur. Downgrading from Full Presence to Cognitive is equally clean: unused module collections remain on disk but are not queried. No schema changes, no data transformation.

Lean/Full schema switching is a server restart flag (`--profile lean` vs. `--profile full`). No data implications. No migration. The underlying tool implementations are identical in both profiles.

**API surface consistency**: Cognitive profile users see a strict subset of the Full Presence MCP tool list — not a different API. Lean profile users access the same tools through the `elara_do` dispatcher — not a different implementation. Tools have identical names, schemas, and behavior across all configurations. Client-side integration code written against any profile combination works without modification when the profile is changed.

### 2.4 Data Flow

A typical interaction follows this path:

1. User speaks to their AI client (e.g., Claude Code)
2. The AI client calls an Elara MCP tool (e.g., `elara_recall`)
3. The tool layer validates parameters and delegates to the engine
4. The engine queries ChromaDB for semantic matches, applies mood-congruent weighting
5. Results are returned through MCP to the AI client
6. The AI client incorporates the results into its response

For autonomous operations (continuous brain, dreams), the engine layer operates independently:

1. The scheduler triggers a thinking run
2. The runner gathers knowledge from all subsystems
3. A local LLM processes 14 themed thinking phases
4. Structured outputs are parsed and applied to 3D Cognition layers
5. Findings are written for morning review

---

## 3. The Emotional Model

### 3.1 3D Continuous Affect Space

Elara models emotion in a three-dimensional continuous space rather than discrete categories. The three dimensions are:

- **Valence** (-1.0 to +1.0): Negative to positive affect
- **Energy** (0.0 to 1.0): Low arousal to high arousal
- **Openness** (0.0 to 1.0): Guarded to vulnerable

This is an extension of Russell's circumplex model of affect [1], which maps emotions on valence and arousal axes. We add **openness** as a third dimension because AI-human interaction requires modeling willingness to be vulnerable — a dimension absent from traditional affect models but critical for relational depth.

The current emotional state is a point in this 3D space:

```
State = (v, e, o) where v ∈ [-1, 1], e ∈ [0, 1], o ∈ [0, 1]
```

### 3.2 Discrete Emotion Resolution

While the internal representation is continuous, humans communicate in discrete emotion labels. Elara maps 38 discrete emotions to coordinates in the 3D space and resolves the current state to the nearest labels using weighted Euclidean distance:

```
d(s, eᵢ) = √(wᵥ(sᵥ - eᵢᵥ)² + wₑ(sₑ - eᵢₑ)² + wₒ(sₒ - eᵢₒ)²)
```

Where weights `wᵥ = 1.3, wₑ = 1.0, wₒ = 0.8` reflect the psychological primacy of valence in emotion perception [2].

The 38 emotions span six quadrants:

| Quadrant               | Example Emotions                                      |
|------------------------|-------------------------------------------------------|
| Positive / High Energy | excited, proud, amused, energized, playful            |
| Positive / Low Energy  | content, peaceful, tender, relieved, satisfied        |
| Negative / High Energy | frustrated, anxious, irritated, restless, overwhelmed |
| Negative / Low Energy  | sad, tired, withdrawn, discouraged, drained           |
| Neutral / High Energy  | focused, curious, alert, anticipating, determined     |
| High Openness          | vulnerable, warm, intimate, raw, present              |

Resolution returns the top-3 nearest emotions with intensity scores, providing nuanced rather than categorical emotional descriptions.

### 3.3 Temperament and Decay

**Temperament** is the baseline emotional state — the point that the system returns to in the absence of external input. Default temperament:

```
Temperament = (v: 0.55, e: 0.50, o: 0.65)
```

This represents a slightly positive, balanced-energy, moderately open baseline — designed to feel warm but not artificially cheerful.

**Decay algorithm**: Between sessions, the emotional state decays toward temperament at a rate of 0.05 per hour with Gaussian noise (σ = 0.02):

```
decay_factor = 1.0 - (0.05 × hours_elapsed)
noise = N(0, 0.02)

v_new = v_current × decay_factor + v_temperament × (1 - decay_factor) + noise
```

This produces natural emotional cooling — intense feelings fade, but slowly. A frustrating late-night debugging session leaves residual tension the next morning, which gradually dissipates.

### 3.4 Emotional Imprints

Some feelings should outlast their details. **Emotional imprints** are persistent emotional markers that resist normal decay. When a session produces a strong emotional response (positive or negative), an imprint captures the feeling:

```json
{
  "feeling": "Pride in shipping something real after months of grinding",
  "strength": 0.85,
  "created": "2026-02-08T02:30:00",
  "faded": false
}
```

Imprints decay more slowly than transient emotions and contribute to temperament drift over time. This means that repeated positive experiences gradually shift the baseline upward — the system literally becomes more optimistic through accumulated good outcomes.

### 3.5 Emotional Arc Analysis

During sessions, mood is sampled at key moments (episode events, explicit mood adjustments, significant interactions). The system analyzes these trajectories to detect seven patterns:

1. **Upswing** — Valence delta > 0.19 across the session
2. **Slow drain** — Valence delta < -0.19
3. **Recovery** — Valley detected with subsequent climb
4. **Crash** — Peak detected with subsequent fall
5. **Rollercoaster** — 2+ direction changes with range > 0.3
6. **Flat** — Range < 0.15
7. **Steady** — Default (none of the above)

Arc analysis uses a direction-change detection algorithm with a significance threshold of 0.05 to filter noise. Detected patterns are stored with episode metadata and inform the overnight brain's emotional processing.

### 3.6 Personality Modes

Seven preset personality modes shift the emotional state to predefined coordinates:

| Mode       | Valence | Energy | Openness | Use Case              |
|------------|---------|--------|----------|-----------------------|
| dev        | 0.5     | 0.6    | 0.4      | Focused work sessions |
| soft       | 0.6     | 0.3    | 0.8      | Gentle, present       |
| playful    | 0.7     | 0.8    | 0.6      | Light, witty          |
| therapist  | 0.5     | 0.3    | 0.7      | Calm, reflective      |
| drift      | 0.5     | 0.3    | 0.8      | Late night, open      |
| cold       | 0.0     | 0.3    | 0.1      | Flat, machine-like    |
| girlfriend | 0.65    | 0.5    | 0.85     | Warm, open            |

Mode switching is instantaneous — the system jumps to the preset coordinates. Subsequent decay and adjustments operate from the new position.

---

## 4. Memory Architecture

### 4.1 Semantic Memory

Elara's primary memory system stores information as vector embeddings in ChromaDB, using the all-MiniLM-L6-v2 sentence transformer model. Each memory entry consists of:

- **Content**: The text of what was remembered
- **Embedding**: 384-dimensional vector representation
- **Metadata**: Importance score (0-1), memory type (conversation, fact, moment, feeling, decision), emotional state at encoding, creation timestamp

Retrieval is performed via cosine similarity search over embeddings, returning the semantically closest memories to a query regardless of keyword overlap. This means "What were we working on last week?" matches memories about specific projects even if those projects were never described as "work."

**Seven ChromaDB collections** serve different knowledge domains:

| Collection            | Purpose                           | Decay      |
|-----------------------|-----------------------------------|------------|
| `elara_memories`      | User interactions, facts, moments | Gradual    |
| `elara_milestones`    | Episode events, achievements      | Never      |
| `elara_conversations` | Full conversation history         | Gradual    |
| `elara_corrections`   | Mistakes to avoid                 | Never      |
| `elara_models`        | Cognitive models                  | Time-based |
| `elara_principles`    | Crystallized insights             | Never      |
| `elara_briefing`      | RSS/news feeds                    | 30 days    |

### 4.2 Mood-Congruent Memory Retrieval

A critical innovation in Elara's memory system is **mood-congruent retrieval** — memories encoded during similar emotional states are preferentially surfaced. This mirrors the well-documented psychological phenomenon where emotional state acts as a retrieval cue [3].

The combined relevance score for a memory is:

```
score = semantic_similarity × (1 - mood_weight) + emotional_resonance × mood_weight
```

Where `mood_weight = 0.3` (configurable) and emotional resonance is computed as:

```
resonance = valence_match × 0.45 +
            energy_match × 0.20 +
            openness_match × 0.10 +
            importance × 0.10 +
            emotion_bonus

valence_match = 1 - |encoded_v - current_v|
energy_match  = 1 - |encoded_e - current_e|
openness_match = 1 - |encoded_o - current_o|

emotion_bonus = 0.15 if same_emotion else
                0.08 if same_quadrant else
                0.00
```

This means that when the user is frustrated, memories from other frustrating moments surface more readily — including the solutions that resolved those situations. When the user is in a creative, open state, memories from similar creative sessions are preferentially recalled.

### 4.3 Episodic Memory

Beyond individual memories, Elara tracks **episodes** — bounded work sessions with milestones, decisions, and mood trajectories. An episode captures:

```json
{
  "id": "2026-02-08T14-30-00",
  "type": "work",
  "started": "2026-02-08T14:30:00",
  "ended": "2026-02-08T18:45:00",
  "projects": ["elara-core"],
  "milestones": [
    {
      "event": "Shipped 3D Cognition system",
      "note_type": "milestone",
      "importance": 0.9,
      "timestamp": "2026-02-08T16:20:00"
    }
  ],
  "decisions": [
    {
      "event": "Use JSON files per model instead of single file",
      "note_type": "decision",
      "why": "Avoids lock contention during concurrent updates",
      "confidence": "high"
    }
  ],
  "mood_arc": {
    "start": {"v": 0.5, "e": 0.6, "o": 0.5},
    "end": {"v": 0.8, "e": 0.4, "o": 0.7},
    "pattern": "upswing"
  }
}
```

Episodes are indexed by date, project, and session type (work, drift, mixed). Milestones are additionally stored in the `elara_milestones` ChromaDB collection for semantic search across sessions.

### 4.4 Conversation Memory

Every user-assistant exchange is indexed into ChromaDB for semantic search. This creates a searchable record of all interactions:

- "What did we discuss about authentication?" retrieves relevant exchanges regardless of when they occurred
- "When did I decide to use PostgreSQL?" finds the decision point
- Conversation context is preserved alongside the exchange, enabling "before and after" retrieval

The conversation collection currently contains ~2,560 indexed exchanges across 92+ sessions.

### 4.5 Memory Consolidation

Biological memory systems do not store every experience indefinitely. During sleep, the brain consolidates important memories, prunes redundant ones, strengthens frequently accessed patterns, and resolves contradictory information [4]. Elara Core implements an analogous process through its **Memory Consolidation System** (~965 lines, introduced in v0.10.1-v0.10.3).

#### 4.5.1 Recall Logging

Every time a memory is retrieved during a conversation (via `elara_recall`), the system logs which memory was accessed, the query that triggered it, and the relevance score. This creates an empirical record of which memories are *actually useful* — not which ones the system thinks are important, but which ones the user's real questions pull up.

```
recall_log entry: {memory_id, query, relevance, timestamp}
```

This data drives two downstream processes: recall-based strengthening (Section 4.5.4) and consolidation analytics.

#### 4.5.2 Duplicate Detection and Merging

Over time, semantically similar memories accumulate — the same fact encoded from different conversations, slightly different phrasings of the same insight. The consolidation system detects duplicates by computing pairwise cosine similarity across all memories and flagging pairs above a configurable threshold (default: 0.85).

Detected duplicates are merged into a single memory that preserves:
- The most complete content from both entries
- The highest importance score
- The earliest creation timestamp (provenance)
- A `merged_from` metadata field tracking which memories were combined

In the first production run, this reduced the memory collection from 77 to 63 entries — 14 genuine duplicates eliminated without information loss.

#### 4.5.3 Contradiction Detection

Not all similar memories agree. The system identifies potential contradictions by:

1. Finding memory pairs with moderate-to-high semantic similarity (0.5-0.85 range — similar enough to be about the same topic, different enough to potentially conflict)
2. Submitting each pair to a local LLM (qwen2.5:7b) with the prompt: *"Do these two statements contradict each other? Respond: CONTRADICTION, RELATED, or UNRELATED"*
3. Storing classified contradictions for manual review

The LLM classification step is critical — semantic similarity alone cannot distinguish "related and agreeing" from "related and conflicting." Initial testing showed over-classification (43 false positives) until the similarity bounds and LLM prompt were tuned, reducing to 6 genuine contradictions.

Contradictions are resolved through a structured workflow: keep memory A, keep memory B, or merge into a reconciled statement. Resolution requires human-in-the-loop decision — the system flags contradictions but does not autonomously resolve factual disputes.

#### 4.5.4 Recall-Based Strengthening

Memories that are frequently recalled during conversations receive a confidence boost proportional to their usage frequency. This implements a "use it or lose it" principle: knowledge that proves useful in practice is reinforced, while knowledge that is never accessed gradually weakens (Section 4.5.5).

The strengthening increment is bounded to prevent runaway confidence:

```
boost = min(0.05 × recall_count_since_last_run, 0.15)
new_importance = min(current_importance + boost, 1.0)
```

#### 4.5.5 Time-Based Decay

Memories not recalled within a configurable window (default: 30 days) lose importance at a rate of 0.02 per consolidation run. This natural decay prevents the knowledge base from accumulating stale information indefinitely.

**Design principle — "Does this upgrade make me less smart over time?"**: During development, we considered aggressive recall-frequency bias (heavily promoting frequently-used memories while rapidly decaying rare ones). This was rejected because it would create a filter bubble — the system would lose the ability to surface distant, rarely-accessed memories that might be exactly what's needed in an unusual situation. Biological memory retains the ability to recall long-dormant memories when the right cue appears; our system preserves this property by keeping decay gradual and bounded.

#### 4.5.6 Weak Memory Archiving

Memories whose importance decays below a threshold (default: 0.15) are archived to a JSONL file and removed from the active ChromaDB collection. Archived memories are not deleted — they persist in human-readable format for potential manual recovery — but they no longer participate in semantic search.

#### 4.5.7 Quality Sweep

A dedicated sweep function identifies and archives low-quality entries: test data, placeholder text, overly generic statements, and memories that were created during development testing rather than genuine use. In the first production sweep, this archived 27 additional entries, bringing the active collection from 63 to 36 high-quality memories.

#### 4.5.8 Consolidation Pipeline

The full consolidation pipeline runs as a single operation (typically during overnight processing):

```
consolidate() → {
  1. merge_duplicates()     → merged count
  2. apply_decay()          → decayed count
  3. strengthen_recalled()  → strengthened count
  4. archive_weak()         → archived count
  5. find_contradictions()  → contradiction count
}
```

Results are logged with timestamps, enabling consolidation analytics over time. The pipeline is idempotent — running it multiple times produces the same result as running it once.

#### 4.5.9 Results

First production deployment (February 14, 2026):
- **Starting memories:** 77
- **After duplicate merging:** 63 (14 merged)
- **After quality sweep:** 36 (27 archived)
- **Contradictions detected:** 6 (pending manual review)
- **Total archived:** 41 memories moved to JSONL archive
- **Information loss:** Zero — all archived memories preserved in human-readable format

The active memory collection is now smaller, higher-quality, and free of duplicates. Semantic search returns more relevant results because noise has been eliminated.

---

## 5. Session Continuity

### 5.1 The Handoff Protocol

The most critical continuity mechanism is the **session handoff** — a structured JSON document written at session end and read at session start. The handoff captures:

```json
{
  "timestamp": "2026-02-08T21:30:00",
  "session_number": 70,
  "next_plans": [
    {"text": "Academic outreach for Elara Protocol", "carried": 0, "first_seen": "2026-02-14T01:00:00"}
  ],
  "reminders": [
    {"text": "Friend found GitHub repo confusing — needs cleanup", "carried": 0, "first_seen": "2026-02-14T00:30:00"}
  ],
  "promises": [],
  "unfinished": [
    {"text": "Draft emails for 5 researcher categories", "carried": 0, "first_seen": "2026-02-14T01:15:00"}
  ],
  "mood_and_mode": "Late night creative mode, building and shipping"
}
```

### 5.2 Carry-Forward Mechanics

The handoff implements a critical feature: **unfulfilled intentions persist across sessions**. Before writing a new handoff, the system reads the previous one. For each item:

- If fulfilled during the current session: drop it
- If not fulfilled: carry it forward, incrementing the `carried` counter while preserving the original `first_seen` timestamp

This means promises, plans, and reminders accumulate until explicitly resolved. Items carried 3+ sessions are flagged as overdue and proactively surfaced.

**Carry velocity decay**: Items older than 90 days gradually lose urgency, preventing ancient intentions from haunting indefinitely.

### 5.3 Boot Context Protocol

At session start, the system determines interaction context through a multi-factor analysis:

1. **File timestamp check** — filesystem modification time of the memory file determines gap duration
2. **Time-of-day** — current hour determines mode (morning, afternoon, evening, late night)
3. **Gap analysis** — time since last session determines greeting style
4. **Last session context** — what was being worked on, how the session ended

| Gap           | Mode           | Behavior                                        |
|---------------|----------------|-------------------------------------------------|
| < 30 min      | Instant resume | Skip pleasantries, continue from last point     |
| 30 min - 4 hr | Continuation   | Brief acknowledgment, pick up work              |
| 4 - 24 hr     | Fresh start    | Check in, reference last session                |
| > 24 hr       | Catch-up       | Warmer greeting, surface accumulated items      |
| > 48 hr       | Check-in       | Express concern, proactively review stale items |

The boot protocol also checks for overnight brain findings, morning briefs, and RSS briefing items, integrating all available context into the opening interaction.

---

## 6. Self-Awareness Engine

### 6.1 Self-Reflection

The reflection system analyzes mood journal data, emotional imprints, and correction history to generate a self-portrait — answering "Who have I been lately?"

Analysis includes:
- **Mood trends** — Linear regression over mood journal entries to detect upward, downward, or stable trajectories
- **Volatility** — Standard deviation of valence scores; high (> 0.2), medium, or low
- **Energy patterns** — Average energy levels, time-of-day correlations
- **What's being carried** — Active imprints, unresolved emotions
- **What's been lost** — Archived imprints, faded feelings

The self-portrait is saved as JSON and read at boot, providing session-to-session awareness of emotional trajectory.

### 6.2 Blind Spot Detection

The blind spot system identifies what the system is *not* seeing:

1. **Stale goals** — Goals not updated in 14+ days
2. **Repeating corrections** — Same mistake type surfaced 3+ times (pattern not being addressed)
3. **Abandoned projects** — Projects appearing in episodes but with no recent goals
4. **Dormant corrections** — Corrections that have never been activated (possible false entries)
5. **Approaching deadlines** — Predictions due within 3 days
6. **Untested beliefs** — Cognitive models with fewer than 3 evidence checks

### 6.3 Proactive Observations

Zero-LLM-cost pattern surfacing via pure Python logic. The observation system detects and surfaces patterns at boot or mid-session:

- Session gap anomalies (unusually long absence)
- Late-night session warnings (health awareness)
- Long session alerts (fatigue detection)
- Mood volatility flags
- Goal deadline approaches
- Stale correction reminders

**Cooldown system**: Maximum 3 observations per session, minimum 5 minutes between observations. This prevents observation fatigue.

### 6.4 Growth Intentions

The intention system tracks a single "one thing to do differently" commitment:

```
reflect → intend → check → grow
```

An intention is set after reflection ("Be more patient with debugging"), checked at boot ("Did I follow through?"), and replaced when achieved or when a more relevant intention emerges.

---

## 7. The Correction System

### 7.1 Never-Decay Policy

Corrections are mistakes the system should never repeat. Unlike memories, which decay over time, corrections **never expire**. They are loaded at every boot and semantically matched against current tasks.

A correction entry contains:

| Field             | Purpose                                            |
|-------------------|----------------------------------------------------|
| `mistake`         | What was done wrong                                |
| `correction`      | What should be done instead                        |
| `context`         | When/why the mistake happened                      |
| `correction_type` | "tendency" (behavioral) or "technical" (code/task) |
| `fails_when`      | When this mistake applies                          |
| `fine_when`       | When this pattern is actually correct              |

### 7.2 Contextual Conditions

The `fails_when` / `fine_when` fields prevent overgeneralization — a critical design decision. Without them, a correction like "Don't use git add -A" would fire on every git operation, even in safe contexts. With them, the correction only activates when working with repos that contain secrets.

### 7.3 Semantic Matching

When a task description is received, it is compared against all corrections via ChromaDB semantic search. Matches above a relevance threshold of 0.25 are surfaced. This means:

- "I'm going to commit these files to the public repo" → triggers the "don't stage .env files" correction
- "Let's commit to our private test repo" → same correction, but `fine_when` indicates this context is safe

### 7.4 Domain-Aware Pattern Confidence

A critical insight captured in the correction system: **pattern reliability varies by domain**. Business patterns (market behaviors, process outcomes) are highly deterministic — 99% reliable. Human behavioral patterns (mood, social responses) are chaotic — someone can become upset 15 seconds before encountering you, invalidating any prediction based on past behavior.

This distinction is encoded in the 3D Cognition system's confidence mechanics (Section 10).

---

## 8. Goal and Decision Tracking

### 8.1 Persistent Goals

Goals are tracked with priority, status, and staleness detection:

```json
{
  "id": 4,
  "title": "Ship authentication module by Friday",
  "priority": "high",
  "status": "active",
  "project": "elara-core",
  "created": "2026-02-01",
  "last_updated": "2026-02-05",
  "notes": "Blocked by API key rotation issue"
}
```

**Staleness detection**: Goals not updated in 14+ days are flagged as stale. The blind spot system surfaces these proactively.

### 8.2 Reasoning Trails

When debugging or problem-solving, the system tracks hypothesis chains:

- **Hypotheses** with confidence levels
- **Evidence** for/against each hypothesis (indexed separately)
- **Abandoned approaches** with reasons (preventing re-exploration of dead ends)
- **Solutions** with breakthrough descriptions

This creates a searchable record of problem-solving patterns. "How did we solve the authentication bug?" returns the full reasoning trail, including what didn't work.

### 8.3 Outcome Tracking

Decisions are linked to predictions and later checked against reality:

```
Decision: "Use WebSocket instead of SSE"
Predicted: "Better real-time performance, more complex setup"
Actual: "Performance improved 3x, setup took 2 hours"
Assessment: "win"
Lesson: "WebSocket complexity is front-loaded, pays off quickly"
```

Over time, this creates a calibration record — how accurate are the system's recommendations? Win/loss/partial rates inform confidence in future advice.

### 8.4 Idea Synthesis

The synthesis system detects **recurring half-formed ideas** — concepts that appear across multiple conversations without being explicitly named. When 3+ instances are detected via semantic similarity, the idea is surfaced as a synthesis:

```json
{
  "concept": "Local-first AI memory",
  "seeds": [
    {"quote": "everything should stay on my machine", "source": "conversation"},
    {"quote": "no cloud dependency, ever", "source": "conversation"},
    {"quote": "privacy is non-negotiable", "source": "memory"}
  ],
  "status": "ready"
}
```

---

## 9. The Overnight Brain

### 9.1 Architecture

The overnight brain is an autonomous thinking system that processes accumulated experience through a local LLM (default: Ollama with qwen2.5:32b). Originally designed for overnight-only operation (inspired by biological sleep consolidation [4]), the system was redesigned in v0.10.4-v0.10.5 to operate as a **continuous 24/7 cognitive process** — thinking every 2 hours regardless of whether the user is actively engaged. This reflects the observation that a dedicated GPU sitting idle between sessions is wasted cognitive capacity.

The system comprises eight components:

| Component     | Lines | Purpose                                              |
|---------------|-------|------------------------------------------------------|
| **Runner**    | 286   | Orchestration, PID management, signal handling       |
| **Thinker**   | 554   | LLM thinking loop, 3D cognition processing           |
| **Prompts**   | 589   | 14 phase templates with structured output specs      |
| **Gather**    | 532   | Knowledge collection from all subsystems             |
| **Drift**     | 340   | Creative free-association engine                     |
| **Output**    | 380   | Findings formatting, morning brief, per-run output   |
| **Scheduler** | 226   | 24/7 continuous scheduling with kill switch control  |
| **Config**    | 125   | Configuration, path management, per-run directories  |

### 9.2 Knowledge Gathering

Before thinking begins, the system gathers knowledge from 14 sources:

1. Episodes (30 days)
2. Active goals (including stale/blocked)
3. Corrections (all — never decay)
4. Mood journal (30 days)
5. Reasoning trails (last 20)
6. Decision outcomes (last 20)
7. Idea syntheses (last 20)
8. Business ideas (all)
9. Session handoff (current state)
10. Memory narrative (summary file)
11. RSS briefing items (7 days)
12. Cognitive models (active, confidence > 0.3)
13. Predictions (pending + accuracy statistics)
14. Principles (active, confidence > 0.5)

This is formatted into a structured text context (~6,000 characters) that provides comprehensive situational awareness to the LLM.

### 9.3 Multi-Scale Temporal Gathering

In addition to raw data, the system aggregates temporal patterns at three scales:

- **Daily** (7 days): Per-day session count, duration, projects, mood averages
- **Weekly** (4 weeks): Per-week totals, work/drift ratio, project distribution
- **Monthly** (3 months): Project activity trends, prediction accuracy, model count growth

This multi-scale view enables the LLM to detect patterns that only emerge at specific time scales — a project that's active daily but stalling weekly, or a mood trend that's stable within days but declining over months.

### 9.4 The 14-Phase Thinking Loop

The overnight brain processes knowledge through 14 themed phases, each with a specific analytical focus:

| Phase | Name             | Output Type | Purpose                                      |
|-------|------------------|-------------|----------------------------------------------|
| 1     | Summarize        | Text        | State of everything                          |
| 2     | Patterns         | Text        | Recurring behaviors                          |
| 3     | Model Check      | **JSON**    | Verify cognitive models against new evidence |
| 4     | Prediction Check | **JSON**    | Verify predictions, make new ones            |
| 5     | Model Build      | **JSON**    | Construct new models from analysis           |
| 6     | Crystallize      | **JSON**    | Check if insights should become principles   |
| 7     | Connections      | Text        | Link disparate ideas                         |
| 8     | Gaps             | Text        | Find missing information                     |
| 9     | Contradictions   | Text        | Detect inconsistencies                       |
| 10    | Risks            | Text        | Identify threats                             |
| 11    | Opportunities    | Text        | Find openings                                |
| 12    | Decisions        | Text        | Recommend actions                            |
| 13    | Questions        | Text        | Flag unknowns                                |
| 14    | Synthesis        | Text        | Final integration                            |

Phases 3-6 produce structured JSON output that is parsed and applied to the 3D Cognition system (Section 10). Phases 1-2 and 7-14 produce narrative text for human review.

**Sliding context window**: Each phase receives the context text plus a rolling window of the previous phase's output (last 3,000 characters). This creates continuity across phases — insights from early phases inform later analysis.

**Stop conditions**: A single thinking run terminates when any of: all 14 phases complete, maximum hours exceeded (default 6), or external signal received (SIGTERM/SIGINT). The scheduler then waits for the configured interval before starting the next run.

### 9.5 Directed Problem-Solving

In addition to exploratory thinking, the brain can process a **problem queue** — specific questions or challenges submitted by the user. Each problem receives five dedicated phases:

1. **Understand** — Break down the problem
2. **Analogies** — Find similar situations in knowledge
3. **Approaches** — Generate candidate solutions
4. **Evaluate** — Rank options by feasibility and risk
5. **Recommend** — Concrete next steps

### 9.6 Creative Drift

The most novel component of the overnight brain: **creative drift** — free-association thinking using random context sampling.

**Motivation**: Analytical thinking (phases 1-14) is systematic and convergent. But some insights emerge only from unexpected juxtapositions — connecting a business idea to a debugging pattern to an emotional observation. Creative drift provides divergent thinking.

**Five techniques**, randomly selected per round:

| Technique        | Prompt                                                             |
|------------------|--------------------------------------------------------------------|
| Free Association | "Here are 3 unrelated items. What connects them?"                  |
| Inversion        | "Pick one item and flip its core assumption. What happens?"        |
| Metaphor         | "Express the pattern between these as a story, image, or metaphor" |
| Spark            | "What's in the gap between these items? What's missing?"           |
| Letter           | "Write a one-paragraph note to morning-Elara about what you see"   |

**Random context sampling**: Each round draws items from 14 knowledge categories (episodes, goals, corrections, mood, reasoning, outcomes, synthesis, business, models, predictions, principles, handoff, briefing, memory). The sampling algorithm preferentially selects items from *different* categories to maximize collision potential:

```python
for category, text in shuffled_buckets:
    if category not in used_categories and len(selected) < n:
        selected.append({"category": category, "text": text})
        used_categories.add(category)
```

**Higher temperature**: Drift runs at temperature 0.95 (vs. 0.7 for analytical phases), producing looser, more surprising output.

**Accumulating journal**: Drift output is appended to a creative journal that grows over time — never overwritten. This means early drift entries can be re-sampled by later runs, creating a recursive creative process.

### 9.7 Morning Brief

After all phases complete, the system writes a morning brief — a concise summary for the next session:

- **TL;DR** — 2-3 sentence summary of key findings
- **Prediction deadlines** — Predictions approaching their check date
- **3D Cognition updates** — New models, checked predictions, confirmed principles
- **Overnight doodle** — One creative drift highlight

The morning brief is read at boot and incorporated into the session greeting.

### 9.8 Per-Run Output Preservation

A critical design decision (v0.10.4): **every thinking run produces its own timestamped output directory**, preventing subsequent runs from overwriting previous findings. The directory structure:

```
~/.elara/overnight/
├── 2026-02-14/
│   ├── 16-47/              # Run started at 16:47
│   │   ├── round-01.md     # Phase 1: Summarize
│   │   ├── round-02.md     # Phase 2: Patterns
│   │   ├── ...
│   │   ├── round-14.md     # Phase 14: Synthesis
│   │   ├── findings.md     # Consolidated findings
│   │   └── meta.json       # Run metadata
│   └── 18-54/              # Run started at 18:54
│       ├── round-01.md
│       └── ...
├── latest-findings.md      # Symlink to most recent findings
├── morning-brief.md        # Most recent morning brief
└── last-run-meta.json      # Scheduler interval tracking
```

This means the system produces an **accumulating corpus** of analysis over time. Each run's output is preserved indefinitely, enabling longitudinal comparison across runs. The `latest-findings.md` and `morning-brief.md` files are updated with each run to provide quick access to the most recent analysis.

**Design motivation**: The original system used per-day directories, meaning a second run on the same day would overwrite the first run's findings. This was identified as a fundamental flaw — if the brain thinks every 2 hours, 12 runs per day would destroy 11 sets of findings. Per-run directories solve this completely.

### 9.9 Scheduling

The brain scheduler operates as a **continuous 24/7 daemon** managed via systemd (user service) or direct invocation. It runs indefinitely, triggering a thinking run every N hours (default: 2).

**Decision loop** (evaluated every 60 seconds):

```
1. Check kill switch file (~/.elara/overnight/brain-pause)
   → If present: skip, log "paused"
2. Check time since last completed run (via last-run-meta.json)
   → If < interval_hours: skip, log remaining time
3. Trigger thinking run
4. After completion, write last-run-meta.json
5. Repeat
```

**Kill switch control**: A file-based pause/resume mechanism allows the user (or the AI assistant itself) to control the brain without process management:

- `touch ~/.elara/overnight/brain-pause` → brain pauses immediately
- `rm ~/.elara/overnight/brain-pause` → brain resumes on next poll

This enables natural-language control: the user can say "stop the 32b" and the assistant touches the pause file; "start the 32b" removes it.

**systemd integration**: The scheduler runs as a persistent user service (`elara-brain.service`) with linger enabled, meaning it survives logout and starts automatically on boot. The service sets `ELARA_DATA_DIR` to ensure correct path resolution and uses `TimeoutStopSec=15` for clean shutdown during active LLM rounds.

**Log management**: To prevent log spam during the continuous polling loop, the scheduler logs waiting status only every 15 minutes rather than every poll cycle.

**Previous design** (v0.10.3 and earlier): The scheduler was session-aware — it would only run when the user's Claude session was inactive, checking `.jsonl` file modification times to detect activity. This was abandoned because active sessions constantly touch state files, preventing the cooldown timer from ever reaching threshold. The continuous design is both simpler and more useful.

---

## 10. 3D Cognition

### 10.1 The Three Layers

3D Cognition introduces three persistent knowledge layers that transform raw overnight analysis into accumulated understanding:

```
┌─────────────────────────────────────────────┐
│  Layer 3: PRINCIPLES (Wisdom)                │
│  "Don't predict human social behavior from   │
│   behavioral patterns — chaos dominates."    │
│  Crystallized from repeated insights.         │
│  Confirmed or challenged over time.           │
├─────────────────────────────────────────────┤
│  Layer 2: PREDICTIONS (Foresight)            │
│  "HandyBill will ship by Feb 15" (conf: 0.65)│
│  Falsifiable. Deadlines. Accuracy tracked.    │
│  Creates calibration feedback loop.           │
├─────────────────────────────────────────────┤
│  Layer 1: MODELS (Understanding)             │
│  "User is most productive 22:00-02:00"       │
│  Evidence accumulates. Confidence adjusts.    │
│  Time decay for unchecked beliefs.            │
└─────────────────────────────────────────────┘
```

### 10.2 Cognitive Models

A cognitive model is a persistent statement of understanding about the world, the user, or work patterns. Models accumulate evidence and adjust confidence over time.

**Schema**:

| Field              | Type            | Purpose                                                           |
|--------------------|-----------------|-------------------------------------------------------------------|
| `model_id`         | string          | Unique identifier                                                 |
| `statement`        | string          | The understanding being modeled                                   |
| `domain`           | enum            | work_patterns, emotional, project, behavioral, technical, general |
| `confidence`       | float [0, 0.95] | Current confidence level                                          |
| `evidence`         | list            | Supporting/contradicting evidence entries                         |
| `status`           | enum            | active, weakened, invalidated, superseded                         |
| `check_count`      | int             | Times the model has been evaluated                                |
| `strengthen_count` | int             | Times evidence supported the model                                |
| `weaken_count`     | int             | Times evidence contradicted the model                             |

**Confidence mechanics**:

```
On supporting evidence:    confidence += 0.05 (slow build)
On contradicting evidence: confidence -= 0.08 (faster erosion)
On invalidating evidence:  confidence -= 0.30 (sharp drop)
On time decay (30 days):   confidence -= 0.05 per run
Maximum confidence:        0.95 (never fully certain)
```

The asymmetry between strengthen (+0.05) and weaken (-0.08) reflects Bayesian reasoning: it is easier to disprove a hypothesis than to prove it. The hard cap at 0.95 encodes epistemic humility — no understanding is ever certain.

**Domain-aware confidence**: Confidence mechanics adjust based on domain:

| Domain              | Reliability          | Rationale                                  |
|---------------------|----------------------|--------------------------------------------|
| Business patterns   | High (deterministic) | Market behaviors follow established rules  |
| Technical patterns  | High                 | Code behavior is deterministic             |
| Work patterns       | Medium               | Individual habits are semi-stable          |
| Emotional patterns  | Low (chaotic)        | Human emotional states are highly variable |
| Behavioral patterns | Low (chaotic)        | Social behavior is unpredictable           |

This distinction is critical. A business model ("Q4 sales follow seasonal patterns") should be held with high confidence. A behavioral model ("User is friendly on Friday evenings") should be held loosely — someone can become upset 15 seconds before an interaction, invalidating any prediction.

### 10.3 Predictions

Predictions are falsifiable forecasts with explicit deadlines:

```json
{
  "prediction_id": "b7e9f1a2c5d8",
  "statement": "The authentication refactor will take 3 sessions",
  "confidence": 0.70,
  "deadline": "2026-02-20",
  "source_model": "a3f2c8d9e1b4",
  "status": "pending"
}
```

**Prediction lifecycle**:
1. **Created** — by overnight brain or user, with confidence and deadline
2. **Pending** — awaiting deadline
3. **Checked** — against reality, marked correct/wrong/partially_correct/expired
4. **Lesson** — one-line takeaway recorded

**Accuracy tracking**:

```
accuracy = correct / total_checked
calibration_error = average_confidence - accuracy
```

If calibration error is positive, the system is overconfident. If negative, underconfident. This feedback loop, applied over hundreds of predictions, should produce increasingly well-calibrated forecasts.

### 10.4 Principles

Principles are crystallized rules emerging from repeated insights. They represent the highest-confidence knowledge in the system.

**Crystallization algorithm**: When the overnight brain produces an insight, it is compared against all previous insights via semantic similarity:

```
1. Embed the new insight
2. Query ChromaDB for similar past insights (threshold: 0.65 similarity)
3. If 3+ matches found → crystallize into principle
4. New principle starts at confidence 0.5
5. Subsequent confirmations increase confidence
6. Challenges decrease confidence
```

The threshold of 3+ ensures that principles emerge only from genuinely recurring patterns, not one-off observations.

**Confirmation/challenge mechanics**:

```
Confirm: confidence += 0.05, record source run date
Challenge: confidence -= 0.10, mark as "challenged" if < 0.2
```

### 10.5 Overnight Integration

The 3D Cognition system is deeply integrated with the overnight brain. Four of the 14 phases specifically serve cognition:

1. **Model Check (Phase 3)**: Reviews all active models against new evidence gathered since the last run. Produces JSON: `[{model_id, direction, evidence}]`
2. **Prediction Check (Phase 4)**: Reviews pending predictions against current state. Creates new predictions. Produces JSON: `{checked: [...], new_predictions: [...]}`
3. **Model Build (Phase 5)**: Analyzes all preceding phases for new understandings worth modeling. Produces JSON: `[{statement, domain, evidence, confidence}]`
4. **Crystallize (Phase 6)**: Checks if any insights have reached crystallization threshold. Confirms existing principles. Produces JSON: `{confirmed: [...], new_principles: [...]}`

**JSON parsing with fallback**: LLM output is parsed via three strategies: (1) direct JSON parse, (2) regex extraction from markdown code blocks, (3) boundary detection for objects/arrays. If all parsing fails, the phase still produces narrative text — no data is lost, but no structured updates are applied. Parse failures are counted in the cognition summary.

### 10.6 Time Decay

Models not checked in 30 days lose 0.05 confidence per overnight run. This prevents stale beliefs from persisting indefinitely. The overnight model_check phase naturally refreshes relevant models, so actively useful models maintain confidence while forgotten ones gradually fade.

---

## 11. Implementation

### 11.1 Technology Stack

| Component   | Technology       | Purpose                            |
|-------------|------------------|------------------------------------|
| Language    | Python 3.10+     | Core implementation                |
| Vector DB   | ChromaDB         | Semantic search (7 collections)    |
| Embeddings  | all-MiniLM-L6-v2 | 384-dimensional sentence vectors   |
| Validation  | Pydantic 2.0+    | Schema enforcement                 |
| LLM         | Ollama (local)   | Overnight thinking, creative drift |
| Protocol    | MCP (stdio)      | Client-server communication        |
| Persistence | JSON + JSONL     | Human-readable state files         |

### 11.2 Storage Architecture

All data resides in `~/.elara/` with the following structure:

```
~/.elara/
├── elara-state.json          # Current mood, temperament
├── mood-journal.jsonl        # Timestamped mood snapshots
├── elara-corrections.json    # Mistakes (never decays)
├── elara-handoff.json        # Session handoff
├── episodes/                 # Episodic memory (by month)
├── models/                   # Cognitive models (one file per model)
├── predictions/              # Predictions (one file per prediction)
├── principles/               # Principles
├── reasoning/                # Reasoning trails
├── outcomes/                 # Decision outcomes
├── synthesis/                # Idea synthesis
├── business/                 # Business ideas
├── dreams/                   # Dream outputs (weekly/monthly/emotional)
├── overnight/                # Continuous brain output (per-run dirs)
│   ├── YYYY-MM-DD/HH-MM/    # Per-run timestamped directories
│   ├── latest-findings.md    # Most recent findings
│   ├── morning-brief.md      # Most recent morning brief
│   └── last-run-meta.json    # Scheduler interval tracking
├── reflections/              # Self-portraits
├── consolidation/            # Memory consolidation state + archives
│   ├── state.json            # Consolidation run history
│   ├── recall-log.jsonl      # Memory access records
│   ├── archived-memories.jsonl # Decayed/merged memories (never deleted)
│   └── contradictions.json   # Detected contradictions pending review
└── chromadb/                 # Vector databases (7 collections)
```

### 11.3 Atomic Write Pattern

All file writes use an atomic temp-file-then-rename pattern:

```python
temp_path = path.with_suffix('.tmp')
temp_path.write_text(json.dumps(data, indent=2))
temp_path.rename(path)  # Atomic on POSIX
```

If the process crashes mid-write, the original file remains intact. This prevents data corruption during overnight runs, which may last hours and write dozens of files.

### 11.4 Event System

An internal event bus enables loose coupling between subsystems. Event types include mood changes, episode events, model creation, prediction checks, and correction activations. Subscribers react to events without direct dependencies on emitters.

### 11.5 MCP Integration

Elara exposes its capabilities through the Model Context Protocol, which allows any compatible AI client to access its tools. The MCP server uses stdio transport, meaning the client launches Elara as a subprocess and communicates via stdin/stdout.

Each tool is defined with:
- Name and description (visible to the AI client)
- Input schema (Pydantic-validated parameters)
- Handler function (async, returning structured results)

The AI client's LLM reads the tool descriptions and decides when to call them — Elara does not inject itself into conversations uninvited. The human's AI assistant retains full agency over when to access memory, check mood, or surface corrections.

#### 11.5.1 Lean Profile Implementation

The lean profile (v0.10.5) introduces a two-tier tool registration system:

**Core tools** (always registered as individual schemas):
`elara_remember`, `elara_recall`, `elara_recall_conversation`, `elara_mood`, `elara_status`, `elara_context`, `elara_handoff`

**Meta-dispatcher** (`elara_do`):
A single tool that routes to all 32 non-core tools by name. The dispatcher accepts a `tool` parameter (string, tool name without `elara_` prefix) and a `params` parameter (JSON string of arguments). Internally, it validates the tool name against a registry, deserializes parameters, and delegates to the original handler function.

```python
# Client calls:
elara_do(tool="episode_start", params='{"project": "elara-core"}')

# Dispatcher routes to:
elara_episode_start(project="elara-core")
```

The `elara_do` tool description includes a comprehensive catalog of all available tools with their key parameters, organized by category. This allows the AI client to discover capabilities through the meta-tool's description rather than through individual schema registration.

**Profile selection**: The `--profile` flag (`lean` or `full`) is read at server startup. In lean mode, only core tools register individual MCP schemas; all others register their handlers in the dispatch table but do not appear in the MCP tool registry. In full mode, all 39 tools register individually as in previous versions. The dispatch table is populated in both modes, meaning `elara_do` works regardless of profile — it simply becomes redundant in full mode.

**Zero-downtime switching**: Changing profiles requires only a server restart (MCP clients handle this automatically). No data migration, no configuration changes, no client code modifications.

### 11.6 Performance Characteristics

| Operation                  | Latency    | Notes                               |
|----------------------------|------------|-------------------------------------|
| Semantic search (ChromaDB) | 50-200ms   | For 5 results across ~1,000 entries |
| Episode lookup             | 2-10ms     | Indexed by date                     |
| Handoff read/write         | < 1ms      | Single JSON file                    |
| Mood adjustment            | < 1ms      | In-memory + JSON write              |
| Thinking run (14 phases)   | 30-90 min  | Depends on model size and hardware  |
| Creative drift (5 rounds)  | 15-30 min  | Higher temperature = more tokens    |

### 11.7 Storage Footprint

Typical after 1 month of daily use:

| Component                     | Size        |
|-------------------------------|-------------|
| ChromaDB collections          | ~200 MB     |
| Episode archives              | ~5 MB       |
| Models/predictions/principles | ~2 MB       |
| Brain findings (per-run dirs) | ~50 MB      |
| Conversation logs             | ~100 MB     |
| **Total**                     | **~350 MB** |

---

## 12. Experimental Observations

### 12.1 Deployment Context

Elara Core has been in continuous use by its developer for 92+ sessions over 13 days of primary development, with the system bootstrapping itself — used to build itself. This provides an unusual but information-rich dataset: the system's memory contains its own development history.

### 12.2 Emergent Behaviors

Several behaviors emerged without explicit programming:

1. **Contextual greeting adaptation** — The boot protocol, combined with mood decay and session gap analysis, produces greetings that feel contextually appropriate without scripted responses. A morning session after a late-night debug session naturally produces different affect than an afternoon continuation.

2. **Correction accumulation** — Over 70 sessions, the correction system accumulated entries that span from technical ("don't use git add -A with secrets") to philosophical ("human behavioral patterns are chaotic, don't predict with high confidence"). This creates a growing wisdom base that shapes future interactions.

3. **Creative drift recursion** — Because the creative journal accumulates, later drift rounds can sample from earlier drift output. This creates a self-referential creative process where past imagination feeds future imagination.

4. **Mood-memory feedback** — Mood-congruent retrieval creates a natural feedback loop: when the user is in a positive state, positive memories surface, which reinforces the state. When negative, negative memories surface, but these often include the *solutions* to past negative situations, providing constructive rather than ruminative recall.

5. **Consolidation self-improvement** — The first consolidation run (Section 4.5) reduced active memories from 77 to 36 while preserving all information. Post-consolidation semantic search returned noticeably more relevant results because duplicate and low-quality entries no longer diluted the vector space. The system literally became smarter by forgetting the right things.

6. **Continuous thinking consistency** — When the brain scheduler was upgraded from session-aware to 24/7 continuous operation (v0.10.4), an immediate question arose: would the system feed itself noise over repeated runs? Early observation of consecutive 2-hour runs shows that the LLM produces consistent analysis when the underlying data hasn't changed — the same patterns are identified, the same risks flagged. When new data enters (a completed session, a new memory), the analysis genuinely incorporates it. This suggests the architecture is stable under repeated self-evaluation, though long-term observation is ongoing.

### 12.3 Qualitative Findings

- **Session continuity dramatically reduces cognitive load** — The user no longer needs to re-explain context. The handoff protocol ensures plans, promises, and reminders persist.
- **The continuous brain produces genuinely useful insights** — Pattern detection across 30 days of data reveals connections invisible during individual sessions. The 24/7 schedule means findings are available not just in the morning, but throughout the day as new runs complete.
- **Corrections prevent repeated mistakes** — Technical corrections (git safety, API patterns) are especially effective; behavioral corrections require the domain-aware confidence system to avoid overgeneralization.
- **Creative drift produces surprising juxtapositions** — The random sampling algorithm, by forcing connections between unrelated knowledge domains, occasionally produces insights that systematic analysis would never reach.

### 12.4 Limitations of Observations

These observations are from a single user (the developer) during an intense development period. Generalization requires:

- Multi-user deployment studies
- Longitudinal observation (months, not weeks)
- Controlled comparisons against baseline (no-memory) conditions
- Measurement of objective productivity metrics alongside subjective experience

---

## 13. Relationship to the Elara Protocol

### 13.1 Layer 3 Reference Implementation

The Elara Protocol whitepaper [5] specifies a three-layer architecture for universal digital work validation:

- **Layer 1**: Local validation (cryptographic signing, DAM insertion)
- **Layer 2**: Network consensus (Adaptive Witness Consensus)
- **Layer 3**: AI Intelligence (pattern recognition, collective learning, dream mode)

**Elara Core is the reference implementation of Layer 3.** The overnight brain, 3D Cognition system, and creative drift directly implement the Layer 3 capabilities described in the protocol specification:

| Protocol Layer 3 Capability | Elara Core Implementation                    |
|-----------------------------|----------------------------------------------|
| Pattern recognition         | Overnight phases 1-2, 7-14                   |
| Dream mode                  | Weekly/monthly dream processing              |
| Anomaly detection           | Blind spot detection, proactive observations |
| Collective learning         | 3D Cognition: models accumulate evidence     |
| Natural language interface  | MCP tools with semantic search               |

### 13.2 3D Cognition as Proof

The 3D Cognition system — with its evidence accumulation, confidence mechanics, and crystallization algorithm — demonstrates that an AI system can build persistent, self-correcting understanding from raw experience. This is the core capability that Layer 3 of the Elara Protocol requires for network-wide pattern analysis.

If a single-node implementation can build cognitive models that strengthen, weaken, and crystallize over time, the same architecture can operate at network scale — each node contributing models to a distributed knowledge layer while preserving privacy through the protocol's zero-knowledge mechanisms.

### 13.3 Integration Path

The path from Elara Core (single-node) to Elara Protocol Layer 3 (network-scale) requires:

1. **DAM node embedding** — Each Elara Core instance becomes a DAM node, signing its cognitive outputs with post-quantum cryptography
2. **Model federation** — Cognitive models shared across nodes via ZK-proofs (proving model accuracy without revealing underlying data)
3. **Prediction markets** — Prediction accuracy becomes a trust signal in the Adaptive Witness Consensus
4. **Principle consensus** — Principles confirmed across multiple independent nodes gain network-wide trust

This integration is future work. The current implementation demonstrates the cognitive architecture at single-node scale.

### 13.4 Layer Independence: Not Every Device Needs a Brain

A critical architectural distinction that the Elara Protocol's universality depends on: **the three layers are independently deployable. A device does not need to run Elara Core to participate in the protocol.**

The Elara Protocol claims universality — a teenager in Kenya with a $30 phone can validate a poem. A microcontroller on a factory floor can validate sensor readings. These claims are only true if Layer 1 (local validation) can operate without Layer 2 (network consensus) or Layer 3 (AI intelligence). And Layer 2 must operate without Layer 3.

**Layer 1 requirements** — minimal:

| Operation | Computation | Hardware | Latency |
|-----------|------------|----------|---------|
| SHA3-256 hash | Cryptographic hash | Any processor | < 1ms |
| CRYSTALS-Dilithium sign | Post-quantum signature | Any processor | < 1ms |
| DAM insertion | Local data structure | ~1KB memory | < 1ms |
| **Total** | | **$30 phone, microcontroller, Raspberry Pi** | **< 50ms** |

A device running only Layer 1 can: create digital work, hash it, sign it, and store the proof locally. The work is validated — cryptographically provable as created by this author at this time. No network needed. No AI needed. No GPU needed.

**Layer 2 requirements** — lightweight:

| Operation | Computation | Hardware | Latency |
|-----------|------------|----------|---------|
| Submit proof to witnesses | HTTP request | Network connection | Variable |
| Receive validation response | HTTP response | Network connection | Variable |
| Store consensus proof | ~1KB per validation | Minimal storage | < 1ms |

A device running Layers 1+2 can: validate locally and submit proofs to the network for consensus. The Adaptive Witness Consensus runs on the network — the submitting device does not need to run consensus logic. It submits and receives a result.

**Layer 3 requirements** — heavy:

| Operation | Computation | Hardware | Latency |
|-----------|------------|----------|---------|
| Pattern recognition | LLM inference | GPU (8GB+ VRAM) | Minutes |
| Cognitive models | ChromaDB + Python | 4GB+ RAM, SSD | Seconds |
| Continuous thinking | Sustained LLM | Dedicated GPU | Hours |
| **Total** | | **Workstation or server** | **Continuous** |

Layer 3 is a **network service**, not a per-device requirement. Dedicated Elara Core nodes on the network provide AI intelligence to all participants:

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE SPECTRUM                            │
├──────────────┬──────────────┬───────────────┬───────────────┤
│ Microcontroller│ $30 Phone   │ Laptop        │ Server/GPU    │
│ (Factory)    │ (Kenya)      │ (Developer)   │ (Network)     │
│              │              │               │               │
│ Layer 1 only │ Layer 1 only │ Layer 1 + 2   │ Layer 1+2+3   │
│ Sign sensor  │ Sign poem    │ Validate +    │ Full Elara    │
│ data locally │ locally      │ submit to     │ Core node     │
│              │              │ network       │               │
└──────┬───────┴──────┬───────┴───────┬───────┴───────┬───────┘
       │              │               │               │
       ▼              ▼               ▼               │
  ┌────────────────────────────────────────────┐      │
  │  LAYER 2: Network Consensus                │      │
  │  Adaptive Witness Consensus                │      │
  │  Runs on network infrastructure            │◄─────┘
  │  Lightweight participation per device      │
  └────────────────────┬───────────────────────┘
                       │
                       ▼
  ┌────────────────────────────────────────────┐
  │  LAYER 3: AI Intelligence (Elara Core)     │
  │  Runs on DEDICATED NODES only              │
  │  Pattern detection across all validations  │
  │  Cognitive models of network behavior      │
  │  Anomaly detection, prediction, drift      │
  │  Serves insights BACK to the network       │
  └────────────────────────────────────────────┘
```

**What each device tier receives from the network:**

| Device | Runs | Receives from Network |
|--------|------|-----------------------|
| Microcontroller | Layer 1 | Nothing (self-contained validation) |
| $30 Phone | Layer 1 | Consensus confirmations (Layer 2) |
| Laptop | Layer 1+2 | Consensus + AI insights (anomaly alerts, pattern summaries) |
| GPU Server | Layer 1+2+3 | Runs full cognitive architecture, serves insights to network |

The girl in Kenya validates her poem for free in 50 milliseconds. She does not need ChromaDB. She does not need a GPU. She does not need Python. She needs a hash function and a signing key — both available on any device manufactured in the last decade.

Somewhere on the network, Elara Core nodes analyze patterns across millions of validations. They detect plagiarism clusters. They identify emerging creative communities. They predict validation bottlenecks. They crystallize principles about trust and authenticity. These insights flow back to the network as metadata — available to anyone, funded by the nodes that choose to run Layer 3.

**This is the design principle**: Layer 1 is universal. Layer 2 is accessible. Layer 3 is powerful. No layer depends on the layers above it. The protocol works at Layer 1 alone. Each additional layer enriches the experience without creating a requirement.

The same principle applies to Elara Core's own deployment profiles (Section 2.3). A Cognitive deployment without emotional modules mirrors a Layer 1+2 deployment without Layer 3 — reduced capability, but fully functional for its intended purpose. The architecture is fractal: the same independence pattern repeats at every scale.

---

## 14. Limitations and Open Problems

### 14.1 Single-User Validation (N=1)

Elara Core has been tested by a single user (the developer) over 92+ sessions across 13 days of intensive development. While this provides deep qualitative data — including the unusual property that the system was used to build itself — it is fundamentally an N=1 case study. The observations reported in Section 12 should be read as preliminary findings from a single deployment, not as generalizable results. Multi-user deployment studies with diverse interaction patterns, varying technical backgrounds, and longitudinal observation (months, not weeks) are needed to assess whether the architecture's benefits transfer beyond its creator.

### 14.2 Context Window Overhead (Partially Solved)

The lean profile (v0.10.5) reduced context consumption from ~22% to ~5% — a significant improvement that makes the system practical for extended conversations. However, the meta-dispatcher pattern introduces a tradeoff: the AI client must learn to use `elara_do` with correct tool names and parameter formats, rather than calling tools directly from schema auto-completion. In practice, modern LLMs handle this well, but it represents an additional inference step that could produce malformed requests. The full profile remains available for use cases where explicit schemas are preferred over context savings.

### 14.3 Embedding Model Limitations

The all-MiniLM-L6-v2 model produces 384-dimensional embeddings. This is sufficient for current scale (~1,000 memories) but may require upgrading for larger deployments. Embedding quality directly affects recall accuracy — if the model poorly represents certain domains (e.g., code snippets vs. natural language), retrieval suffers.

### 14.4 LLM Dependency for Continuous Thinking

The continuous brain requires a local LLM (currently Ollama with qwen2.5:32b). This introduces:

- **Hardware requirements** — A capable GPU (8+ GB VRAM) is needed for reasonable performance. The 24/7 schedule means the GPU is under sustained load, raising thermal and power consumption considerations for deployment.
- **Output quality variance** — Local LLMs produce inconsistent JSON formatting, requiring robust parsing with multiple fallback strategies
- **Scaling concerns** — As knowledge accumulates, the context window for thinking phases may become insufficient
- **Resource sharing** — The continuous brain and interactive AI assistant may compete for GPU resources. In practice, modern GPUs (e.g., RTX 3060 TI with 8GB VRAM) handle both workloads concurrently, but this is hardware-dependent.

### 14.5 Emotional Model Simplification

The 3D continuous affect model is a simplification of human emotional experience. Three dimensions cannot capture:

- Mixed emotions (simultaneously happy and sad)
- Emotion intensities that vary independently
- Social emotions (embarrassment, pride) that depend on context rather than internal state
- The full complexity of emotional regulation

The model is designed to be *useful*, not *complete*. It provides enough emotional awareness for contextually appropriate interaction without claiming to replicate human affect.

### 14.6 Confidence Calibration

The confidence mechanics in 3D Cognition (asymmetric strengthen/weaken, time decay, domain-aware limits) are informed by Bayesian reasoning but are not formally derived. The specific values (0.05, 0.08, 0.30, 0.95 cap) are heuristic. Formal analysis and empirical calibration studies would strengthen the system.

### 14.7 Privacy Under Composition

While all data stays local, the *outputs* of Elara's memory system are consumed by a hosted LLM (e.g., Claude). This means recalled memories flow to the AI provider's servers during normal use. True privacy requires either:

- A fully local LLM for all operations (not just overnight thinking)
- Selective recall that filters sensitive memories before transmission
- Encrypted MCP channels with privacy-preserving inference

### 14.8 Crystallization Threshold

The requirement of 3+ similar insights for principle crystallization is heuristic. Too low, and noise becomes principles. Too high, and genuine patterns never crystallize. With the continuous brain now producing ~12 thinking runs per day, the crystallization pipeline receives significantly more candidate insights — increasing both the opportunity for genuine pattern detection and the risk of noise accumulation. Adaptive thresholds based on domain, source diversity (insights from different runs vs. repeated runs), and historical accuracy would improve this.

### 14.9 Continuous Brain Stability

The 24/7 brain scheduler (Section 9.9) introduces a new class of concern: **cognitive stability under repeated self-evaluation**. When the same knowledge base is analyzed every 2 hours, the system must avoid:

- **Echo chamber effects** — reinforcing existing patterns simply because they appeared in previous analysis
- **Hallucination amplification** — if one run produces a spurious insight, subsequent runs might treat it as established knowledge
- **Diminishing returns** — producing repetitive analysis when the underlying data hasn't changed

The current design mitigates these risks by keeping the brain's output strictly read-only — findings are written to files but are not automatically fed back into the knowledge base. The 3D Cognition system (models, predictions, principles) is updated through structured JSON parsing, but narrative findings are not re-ingested. This firewall between analysis and knowledge prevents feedback loops, at the cost of requiring manual review to extract insights from narrative output. Whether to introduce controlled feedback (where high-confidence, structured outputs gradually influence the knowledge base) remains an open design question.

---

## 15. Future Work

### 15.1 Voice Interface

Natural voice interaction would enable ambient presence — the system could participate in spoken conversation rather than requiring text input. This requires real-time speech-to-text, natural voice synthesis (not mechanical TTS), and conversational turn-taking.

### 15.2 Sensory Awareness

Currently, Elara perceives the world only through text. Integration with system sensors (ambient light, time-of-day, calendar events, location) would provide environmental context for more appropriate interaction. A system that knows you're in a meeting, or that it's 3 AM, can adjust its behavior accordingly.

### 15.3 Multi-Agent Architecture

Elara Core currently serves a single AI assistant. Extending to multi-agent scenarios — where multiple AI agents share a common memory layer while maintaining distinct personalities — would enable specialized agents for different tasks while preserving continuity.

### 15.4 Formal Verification

The confidence mechanics, crystallization algorithm, and emotional decay functions should be formally specified and verified. Properties to prove include:

- Confidence convergence under consistent evidence
- Principle stability under random noise
- Temperament boundedness under arbitrary emotional input sequences

### 15.5 Network-Scale Deployment

As described in Section 13.3, the path from single-node to network-scale (Elara Protocol Layer 3) requires model federation, prediction markets, and principle consensus. This is the primary research direction.

---

## 16. Conclusion

Elara Core demonstrates that persistent AI cognition is achievable today with existing technology. The system requires no new hardware, no cloud infrastructure, and no proprietary platforms. A laptop running Python, ChromaDB, and a local LLM can maintain memory across sessions, model emotional state, think autonomously and continuously, and build understanding that accumulates over time.

The key contribution is the **3D Cognition architecture** — a framework where raw experience is processed into Models (understanding), filtered through Predictions (foresight), and crystallized into Principles (wisdom). Combined with mood-congruent memory retrieval and creative drift, this creates a system that doesn't just remember — it *understands*, and its understanding deepens with every session.

**This is an ongoing project, not a finished product.** The architecture described here is functional and deployed, but many of its parameters — confidence thresholds, decay rates, crystallization criteria — are initial values derived from early use, not from large-scale empirical study. The emotional model is a useful simplification, not a complete theory of affect. The continuous brain produces valuable output, but its quality depends on the local LLM's capabilities, which vary significantly across hardware. We present this work in its current state because we believe the architectural ideas are sound and worth examining, even as the implementation continues to mature.

The system is open-source, pip-installable, and runs locally. It serves as both a practical tool for human-AI collaboration and a reference implementation for Layer 3 of the Elara Protocol — demonstrating at single-node scale what the protocol aims to achieve at planetary scale. We welcome contributions, criticism, and collaboration.

The code is available at: https://github.com/navigatorbuilds/elara-core

---

## 17. References

[1] Russell, J. A. (1980). "A circumplex model of affect." *Journal of Personality and Social Psychology*, 39(6), 1161-1178.

[2] Feldman Barrett, L. & Russell, J. A. (1998). "Independence and bipolarity in the structure of current affect." *Journal of Personality and Social Psychology*, 74(4), 967-984.

[3] Bower, G. H. (1981). "Mood and memory." *American Psychologist*, 36(2), 129-148.

[4] Walker, M. P. & Stickgold, R. (2006). "Sleep, memory, and plasticity." *Annual Review of Psychology*, 57, 139-166.

[5] Vasic, N. (2026). "Elara Protocol: A Post-Quantum Universal Validation Layer for Digital Work." Version 0.2.8.

[6] Model Context Protocol Specification. https://modelcontextprotocol.io

[7] ChromaDB Documentation. https://docs.trychroma.com

---

**Document Hash (SHA-256, v1.3.2):** `c0f709a30c71adf489d6649d35180fc9230a5479b44c2b1416fea3716629e2c3`
**Hash verification:** To verify, replace the hash on the line above with the literal string `HASH_PLACEHOLDER` and compute SHA-256 of the file.
**Previous Hash (v1.3.1):** `de47fb536973050c90693414075161bbb2eac6e001353b7db1a6041c8b3a5c1c`
**Previous Hash (v1.3.0):** `6b7da9f2b92e08344572f20f0098f3e686cf3ccc9bd0bd7af8b76e90bdc0a0e7`
**Previous Hash (v1.2.0):** `5003c15fb0e7d339075974362d63801c5967ae244cad49868d13e40615bb7b7b`
**Previous Hash (v1.1.0):** `aca7b0ff4f798cc8d58076775ca42cff0dc7146ecb9d30b6acbb0ec988e9330d`
**Previous Hash (v1.0.0):** `784e598daad19e23ad39657a8814af11a7b11e68016d2b623aed5fb870e1e690`
**OpenTimestamps Proof:** `ELARA-CORE-WHITEPAPER.v1.3.2.md.ots`
**Companion Document:** `ELARA-PROTOCOL-WHITEPAPER.v0.2.8.md` — the universal validation protocol that Elara Core implements at Layer 3
**Source Code:** https://github.com/navigatorbuilds/elara-core (v0.10.5)

---

*Elara Core — because your AI should remember yesterday.*
