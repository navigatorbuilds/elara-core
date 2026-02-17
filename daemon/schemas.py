# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Schema Registry — Pydantic models for all JSON structures.

Single source of truth for every JSON file Elara reads/writes.
Catches field drift, type mismatches, and missing fields at load time.

Usage:
    from daemon.schemas import Handoff, Goal, ElaraState

    # Validate on load
    data = json.loads(path.read_text())
    handoff = Handoff.model_validate(data)

    # Serialize on save
    path.write_text(handoff.model_dump_json(indent=2))

All models use extra="allow" so existing data with unknown fields
won't break — we just won't validate those extra fields.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Base config — all models inherit this
# ============================================================================

class ElaraModel(BaseModel):
    """Base for all Elara schemas. Allows extra fields for forward compat."""
    model_config = {"extra": "allow"}


# ============================================================================
# Custom exceptions — standardized error handling across daemon layer
# ============================================================================

class ElaraNotFoundError(Exception):
    """Raised when a requested item (trail, idea, goal, etc.) doesn't exist."""

class ElaraValidationError(Exception):
    """Raised when input fails validation (bad status, out-of-range index, etc.)."""


# ============================================================================
# MOOD & STATE
# ============================================================================

class MoodVector(ElaraModel):
    """3D mood space: valence (-1 to 1), energy (0 to 1), openness (0 to 1)."""
    valence: float = 0.55
    energy: float = 0.5
    openness: float = 0.65


class Imprint(ElaraModel):
    """Emotional imprint — a persistent feeling that outlasts details."""
    feeling: str
    strength: float = 0.7
    created: Optional[str] = None
    imprint_type: Optional[str] = Field(None, alias="type")
    decay_rate: Optional[float] = None
    source_episode: Optional[str] = None


class Consolidation(ElaraModel):
    """Sleep/idle consolidation tracking."""
    last_idle_start: Optional[str] = None
    last_idle_quality: Any = None  # float or string like "long_absence"
    sleep_debt: float = 0


class SessionFlags(ElaraModel):
    """Session-level behavioral flags."""
    had_deep_conversation: bool = False
    user_seemed_stressed: bool = False
    user_seemed_happy: bool = False
    late_night_session: bool = False
    long_session: bool = False


class CurrentSession(ElaraModel):
    """Active session tracking within state."""
    id: Optional[str] = None
    type: Optional[str] = None
    started: Optional[str] = None
    projects: List[str] = Field(default_factory=list)
    auto_detected_type: Optional[str] = None


class ElaraState(ElaraModel):
    """Main state file: ~/.claude/elara-state.json"""
    mood: MoodVector = Field(default_factory=MoodVector)
    temperament: MoodVector = Field(default_factory=MoodVector)
    imprints: List[Imprint] = Field(default_factory=list)
    residue: List[Dict[str, Any]] = Field(default_factory=list)
    last_update: Optional[str] = None
    last_session_end: Optional[str] = None
    consolidation: Consolidation = Field(default_factory=Consolidation)
    session_mood_start: Optional[Dict[str, float]] = None
    allostatic_load: float = 0
    flags: SessionFlags = Field(default_factory=SessionFlags)
    current_session: CurrentSession = Field(default_factory=CurrentSession)


class MoodJournalEntry(ElaraModel):
    """Single entry in mood journal JSONL."""
    ts: str
    v: float
    e: float
    o: float
    emotion: Optional[str] = None
    reason: Optional[str] = None
    trigger: str = "adjust"
    episode: Optional[str] = None


class ImplantArchiveEntry(ElaraModel):
    """Archived imprint entry in JSONL."""
    archived: str
    feeling: str
    strength: float = 0.7


class TemperamentLogEntry(ElaraModel):
    """Single temperament adjustment in JSONL."""
    timestamp: str
    adjustments: Optional[Dict[str, float]] = None
    # Older format had flat fields
    valence_delta: Optional[float] = None
    energy_delta: Optional[float] = None
    openness_delta: Optional[float] = None
    reason: Optional[str] = None


# ============================================================================
# HANDOFF
# ============================================================================

class HandoffItem(ElaraModel):
    """Single item in a handoff list (plan, reminder, promise, unfinished)."""
    text: str
    carried: int = 0
    first_seen: str
    expires: Optional[str] = None


class Handoff(ElaraModel):
    """Session handoff: ~/.claude/elara-handoff.json"""
    timestamp: str
    session_number: int
    next_plans: List[HandoffItem] = Field(default_factory=list)
    reminders: List[HandoffItem] = Field(default_factory=list)
    promises: List[HandoffItem] = Field(default_factory=list)
    unfinished: List[HandoffItem] = Field(default_factory=list)
    mood_and_mode: str = ""


# ============================================================================
# GOALS
# ============================================================================

class Goal(ElaraModel):
    """Single goal: stored in ~/.claude/elara-goals.json (list)."""
    id: int
    title: str
    project: Optional[str] = None
    status: str = "active"
    priority: str = "medium"
    created: str
    last_touched: str
    notes: Optional[str] = None


# ============================================================================
# CORRECTIONS
# ============================================================================

class Correction(ElaraModel):
    """Single correction: stored in ~/.claude/elara-corrections.json (list)."""
    id: int
    mistake: str
    correction: str
    context: Optional[str] = None
    correction_type: str = "tendency"
    fails_when: Optional[str] = None
    fine_when: Optional[str] = None
    date: str
    last_activated: Optional[str] = None
    times_surfaced: int = 0
    times_dismissed: int = 0


# ============================================================================
# REASONING TRAILS
# ============================================================================

class Hypothesis(ElaraModel):
    """Single hypothesis within a reasoning trail."""
    h: str
    evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    outcome: Optional[str] = None
    added: Optional[str] = None


class ReasoningTrail(ElaraModel):
    """Reasoning trail: ~/.claude/elara-reasoning/{trail_id}.json"""
    trail_id: str
    started: str
    context: str
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    abandoned_approaches: List[str] = Field(default_factory=list)
    final_solution: Optional[str] = None
    breakthrough_trigger: Optional[str] = None
    resolved: bool = False
    tags: List[str] = Field(default_factory=list)


# ============================================================================
# OUTCOMES
# ============================================================================

class Outcome(ElaraModel):
    """Decision outcome: ~/.claude/elara-outcomes/{outcome_id}.json"""
    outcome_id: str
    decision: str
    context: str
    reasoning_trail: Optional[str] = None
    predicted: str
    actual: Optional[str] = None
    assessment: str = "too_early"
    lesson: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    recorded: str
    checked: Optional[str] = None
    # Pitch extensions
    pitches: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# BUSINESS IDEAS
# ============================================================================

class Competitor(ElaraModel):
    """Business competitor entry."""
    name: str
    strengths: Optional[str] = None
    weaknesses: Optional[str] = None
    url: Optional[str] = None
    added: Optional[str] = None


class IdeaScore(ElaraModel):
    """5-axis viability score."""
    problem: int = Field(default=0, ge=0, le=5)
    market: int = Field(default=0, ge=0, le=5)
    effort: int = Field(default=0, ge=0, le=5)
    monetization: int = Field(default=0, ge=0, le=5)
    fit: int = Field(default=0, ge=0, le=5)
    total: int = Field(default=0, ge=0, le=25)
    scored_at: Optional[str] = None


class BusinessIdea(ElaraModel):
    """Business idea: ~/.claude/elara-ideas/{idea_id}.json"""
    idea_id: str
    name: str
    description: str
    target_audience: str = ""
    your_angle: str = ""
    competitors: List[Competitor] = Field(default_factory=list)
    score: Optional[IdeaScore] = None
    status: str = "exploring"
    tags: List[str] = Field(default_factory=list)
    reasoning_trails: List[str] = Field(default_factory=list)
    outcomes: List[str] = Field(default_factory=list)
    notes: List[Dict[str, Any]] = Field(default_factory=list)
    created: str
    last_touched: str


# ============================================================================
# SYNTHESIS
# ============================================================================

class SynthesisSeed(ElaraModel):
    """Single seed (evidence) for a synthesized idea."""
    quote: str
    source: str = "conversation"
    date: Optional[str] = None


class Synthesis(ElaraModel):
    """Idea synthesis: ~/.claude/elara-synthesis/{synthesis_id}.json"""
    synthesis_id: str
    concept: str
    status: str = "dormant"
    seeds: List[SynthesisSeed] = Field(default_factory=list)
    created: Optional[str] = None
    last_seed: Optional[str] = None
    confidence: float = 0.0
    times_surfaced: int = 0
    first_seen: Optional[str] = None
    last_reinforced: Optional[str] = None
    activated_at: Optional[str] = None
    implemented_at: Optional[str] = None
    abandoned_at: Optional[str] = None


# ============================================================================
# PRESENCE & CONTEXT
# ============================================================================

class Presence(ElaraModel):
    """Presence state: ~/.claude/elara-presence.json"""
    last_seen: Optional[str] = None
    session_start: Optional[str] = None
    total_sessions: int = 0
    total_time_together: float = 0
    longest_absence: float = 0
    history: List[Dict[str, Any]] = Field(default_factory=list)


class ContextConfig(ElaraModel):
    """Context toggle: ~/.claude/elara-context-config.json"""
    enabled: bool = True


class Context(ElaraModel):
    """Quick context: ~/.claude/elara-context.json"""
    topic: Optional[str] = None
    last_exchange: Optional[str] = None
    task_in_progress: Optional[str] = None
    updated: Optional[str] = None
    updated_ts: Optional[int] = None


# ============================================================================
# USER STATE
# ============================================================================

class UserStateSignal(ElaraModel):
    """Inferred user state from signals."""
    energy: float = 0.5
    energy_confidence: float = 0.2
    focus: float = 0.5
    focus_confidence: float = 0.2
    engagement: float = 0.5
    engagement_confidence: float = 0.2
    frustration: float = 0.0
    frustration_confidence: float = 0.2
    suggested_approach: Optional[str] = None
    timestamp: Optional[str] = None


# ============================================================================
# AWARENESS
# ============================================================================

class Intention(ElaraModel):
    """Growth intention: ~/.claude/elara-intention.json"""
    current: Optional[Dict[str, Any]] = None
    previous: Optional[Dict[str, Any]] = None


# ============================================================================
# DREAMS
# ============================================================================

class DreamStatus(ElaraModel):
    """Dream schedule: ~/.claude/elara-dreams/status.json"""
    last_weekly: Optional[str] = None
    last_monthly: Optional[str] = None
    last_threads: Optional[str] = None
    last_emotional: Optional[str] = None
    weekly_count: int = 0
    monthly_count: int = 0
    emotional_count: int = 0


# ============================================================================
# EPISODES
# ============================================================================

class Milestone(ElaraModel):
    """Episode milestone."""
    event: str
    importance: float = 0.5
    timestamp: Optional[str] = None
    note_type: str = "milestone"
    project: Optional[str] = None


class Decision(ElaraModel):
    """Episode decision."""
    what: str
    why: Optional[str] = None
    confidence: str = "medium"
    project: Optional[str] = None
    timestamp: Optional[str] = None


class Episode(ElaraModel):
    """Single episode: ~/.claude/elara-episodes/{YYYY-MM}/{id}.json"""
    id: str
    started: str
    ended: Optional[str] = None
    session_type: str = "work"
    projects: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    was_meaningful: bool = False
    milestones: List[Milestone] = Field(default_factory=list)
    decisions: List[Decision] = Field(default_factory=list)
    mood_start: Optional[Dict[str, float]] = None
    mood_end: Optional[Dict[str, float]] = None
    mood_trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    duration_minutes: Optional[int] = None


class EpisodeIndex(ElaraModel):
    """Episodes index: ~/.claude/elara-episodes/index.json"""
    episodes: List[str] = Field(default_factory=list)
    by_project: Dict[str, List[str]] = Field(default_factory=dict)
    by_date: Dict[str, List[str]] = Field(default_factory=dict)
    last_episode_id: Optional[str] = None
    total_episodes: int = 0


# ============================================================================
# GMAIL
# ============================================================================

class GmailCache(ElaraModel):
    """Gmail sync state: ~/.claude/elara-gmail-cache.json"""
    last_history_id: Optional[str] = None
    last_sync: Optional[str] = None
    indexed_count: int = 0


# ============================================================================
# OVERNIGHT
# ============================================================================

class OvernightConfig(ElaraModel):
    """Overnight thinking config: ~/.claude/overnight/overnight-config.json"""
    max_hours: float = 6.0
    stop_at: str = "07:00"
    think_model: str = "qwen2.5:32b"
    mode: str = "auto"  # auto, exploratory, directed
    rounds_per_problem: int = 5
    max_tokens: int = 2048
    temperature: float = 0.7
    enable_research: bool = True
    # 3D Cognition
    schedule_mode: str = "session_aware"  # session_aware | scheduled
    scheduled_interval_hours: float = 6.0
    enable_3d_cognition: bool = True


# ============================================================================
# 3D COGNITION — Models, Predictions, Principles
# ============================================================================

class ModelEvidence(ElaraModel):
    """Single piece of evidence for a cognitive model."""
    text: str
    source: str = "overnight"  # overnight, observation, correction, manual
    direction: str = "supports"  # supports, weakens, invalidates
    date: str = ""


class CognitiveModel(ElaraModel):
    """Persistent understanding: ~/.elara/elara-models/{model_id}.json"""
    model_id: str
    statement: str
    domain: str = "general"  # work_patterns, emotional, project, behavioral, technical, general
    confidence: float = 0.5
    evidence: List[ModelEvidence] = Field(default_factory=list)
    status: str = "active"  # active, weakened, invalidated, superseded
    check_count: int = 0
    strengthen_count: int = 0
    weaken_count: int = 0
    created: str = ""
    last_updated: str = ""
    last_checked: str = ""
    source_run: str = ""
    tags: List[str] = Field(default_factory=list)


class Prediction(ElaraModel):
    """Explicit forecast: ~/.elara/elara-predictions/{prediction_id}.json"""
    prediction_id: str
    statement: str
    confidence: float = 0.5
    deadline: str = ""  # ISO date
    source_model: Optional[str] = None  # model_id link
    source_run: str = ""
    status: str = "pending"  # pending, correct, wrong, partially_correct, expired
    actual_outcome: Optional[str] = None
    lesson: Optional[str] = None
    checked: Optional[str] = None
    created: str = ""
    tags: List[str] = Field(default_factory=list)


class Principle(ElaraModel):
    """Crystallized self-derived rule: stored in elara-principles.json (list)."""
    principle_id: str
    statement: str
    domain: str = "general"
    confidence: float = 0.5
    source_insights: List[str] = Field(default_factory=list)  # list of run dates
    source_models: List[str] = Field(default_factory=list)  # list of model_ids
    status: str = "active"  # active, challenged, retired
    times_confirmed: int = 0
    times_challenged: int = 0
    last_confirmed: Optional[str] = None
    created: str = ""
    tags: List[str] = Field(default_factory=list)


class WorkflowStep(ElaraModel):
    """Single step in a workflow pattern."""
    action: str                          # imperative: "update README versions section"
    artifact: Optional[str] = None       # file/resource affected
    depends_on_previous: bool = True     # sequential by default


class WorkflowPattern(ElaraModel):
    """Learned action sequence: ~/.elara/elara-workflows/{workflow_id}.json"""
    workflow_id: str
    name: str                            # "whitepaper release flow"
    domain: str = "development"          # development, deployment, documentation, maintenance
    trigger: str                         # "whitepaper version updated"
    steps: List[WorkflowStep] = Field(default_factory=list)
    confidence: float = 0.5
    source_episodes: List[str] = Field(default_factory=list)
    times_matched: int = 0
    times_completed: int = 0
    times_skipped: int = 0
    status: str = "active"              # active, evolved, retired
    created: Optional[str] = None
    last_matched: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class OvernightQueueItem(ElaraModel):
    """Single problem in the overnight directed-thinking queue."""
    problem: str
    context: str = ""
    priority: int = Field(default=5, ge=1, le=10)
    added: str = ""
    source: str = "manual"  # manual, handoff, correction, goal


class OvernightMeta(ElaraModel):
    """Run metadata: ~/.claude/overnight/YYYY-MM-DD/meta.json"""
    date: str
    started: str
    ended: Optional[str] = None
    mode: str = "exploratory"
    rounds_completed: int = 0
    problems_processed: int = 0
    research_queries: int = 0
    status: str = "running"  # running, completed, stopped, error
    config: Optional[Dict[str, Any]] = None


# ============================================================================
# KNOWLEDGE GRAPH
# ============================================================================

class KnowledgeNode(ElaraModel):
    """Single node in the knowledge graph — addressed by 6-tuple."""
    id: str
    semantic_id: str
    time: Optional[str] = None
    source_doc: Optional[str] = None
    source_section: Optional[str] = None
    source_line: Optional[int] = None
    type: str = "reference"  # definition|reference|metric|constraint|dependency
    granularity: str = "section"  # token|line|section|document|corpus
    confidence: float = 0.5
    content: Optional[str] = None
    created: Optional[str] = None


class KnowledgeEdge(ElaraModel):
    """Directed edge between nodes or between a node and a document."""
    id: str
    source_node: str
    target_node: Optional[str] = None
    target_doc: Optional[str] = None
    edge_type: str  # defines|references|contradicts|depends_on|evolves_to|missing_from
    confidence: float = 0.5
    explanation: Optional[str] = None
    created: Optional[str] = None


class KnowledgeDocument(ElaraModel):
    """Indexed document registry entry."""
    doc_id: str
    version: str
    path: Optional[str] = None
    indexed_at: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0


class KnowledgeAlias(ElaraModel):
    """Maps variant names to a canonical semantic_id."""
    semantic_id: str
    alias: str


# ============================================================================
# UTILITY — validated load/save helpers
# ============================================================================

import json
import os
from pathlib import Path
from typing import Type, TypeVar

T = TypeVar("T", bound=ElaraModel)


def load_validated(path: Path, schema: Type[T], default: Any = None) -> T:
    """
    Load JSON from file and validate against schema.

    Args:
        path: Path to JSON file
        schema: Pydantic model class to validate against
        default: Default value if file doesn't exist or is invalid.
                 If None, returns schema() with all defaults.
    """
    if not path.exists():
        if default is not None:
            return schema.model_validate(default)
        return schema()

    try:
        data = json.loads(path.read_text())
        return schema.model_validate(data)
    except (json.JSONDecodeError, Exception):
        if default is not None:
            return schema.model_validate(default)
        return schema()


def _atomic_rename(tmp: Path, dest: Path):
    """Flush, fsync, then rename — crash-safe atomic write."""
    fd = os.open(str(tmp), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rename(str(tmp), str(dest))


def save_validated(path: Path, model: ElaraModel, atomic: bool = True):
    """
    Save a validated model to JSON file.

    Args:
        path: Destination path
        model: Pydantic model instance
        atomic: If True, write to .tmp then rename (default: True)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = model.model_dump_json(indent=2, exclude_none=False)

    if atomic:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        _atomic_rename(tmp, path)
    else:
        path.write_text(content)


def load_validated_list(path: Path, schema: Type[T]) -> List[T]:
    """Load a JSON array and validate each item."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            return []
        return [schema.model_validate(item) for item in data]
    except (json.JSONDecodeError, Exception):
        return []


def save_validated_list(path: Path, items: List[ElaraModel], atomic: bool = True):
    """Save a list of validated models to JSON array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps([item.model_dump() for item in items], indent=2)

    if atomic:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        _atomic_rename(tmp, path)
    else:
        path.write_text(content)


def atomic_write_json(path: Path, data: Any, indent: int = 2):
    """Atomically write a dict/list as JSON (write .tmp, then rename).

    For raw dicts that don't have matching Pydantic schemas.
    For schema-validated data, use save_validated() instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent))
    _atomic_rename(tmp, path)
