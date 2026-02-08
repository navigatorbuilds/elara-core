"""Tier 1: Schema round-trip tests — save, load, verify no data loss."""

import json
import pytest
from pathlib import Path
from datetime import datetime

from daemon.schemas import (
    # Models
    MoodVector, Imprint, Consolidation, SessionFlags, CurrentSession, ElaraState,
    MoodJournalEntry, ImplantArchiveEntry, TemperamentLogEntry,
    HandoffItem, Handoff, Goal, Correction,
    Hypothesis, ReasoningTrail, Outcome,
    Competitor, IdeaScore, BusinessIdea, SynthesisSeed, Synthesis,
    Presence, ContextConfig, Context, UserStateSignal, Intention, DreamStatus,
    Milestone, Decision, Episode, EpisodeIndex, GmailCache,
    # Functions
    save_validated, load_validated, save_validated_list, load_validated_list,
    atomic_write_json,
    # Exceptions
    ElaraNotFoundError, ElaraValidationError,
)


# ============================================================================
# Schema round-trip: create → save → load → compare
# ============================================================================

# Models that have all-optional/default fields — can instantiate with no args
SCHEMA_NO_ARGS = [
    MoodVector, Consolidation, SessionFlags, CurrentSession, IdeaScore,
    Presence, ContextConfig, Context, UserStateSignal, Intention,
    DreamStatus, EpisodeIndex, GmailCache,
]

# Models with required fields — provide minimal kwargs
NOW = "2026-01-01T00:00:00"
SCHEMA_WITH_ARGS = [
    (Imprint, {"feeling": "warm"}),
    (MoodJournalEntry, {"ts": NOW, "v": 0.5, "e": 0.5, "o": 0.5}),
    (ImplantArchiveEntry, {"archived": NOW, "feeling": "calm"}),
    (TemperamentLogEntry, {"timestamp": NOW}),
    (HandoffItem, {"text": "test plan", "first_seen": NOW}),
    (Handoff, {"timestamp": NOW, "session_number": 1}),
    (Goal, {"id": 1, "title": "test", "created": NOW, "last_touched": NOW}),
    (Correction, {"id": 1, "mistake": "oops", "correction": "fix it", "date": NOW}),
    (Hypothesis, {"h": "maybe a race condition"}),
    (ReasoningTrail, {"trail_id": "t1", "started": NOW, "context": "flaky test"}),
    (Outcome, {"outcome_id": "o1", "decision": "go", "context": "ctx", "predicted": "win", "recorded": NOW}),
    (Competitor, {"name": "Acme Inc"}),
    (SynthesisSeed, {"quote": "we keep saying this"}),
    (Synthesis, {"synthesis_id": "s1", "concept": "recurring idea"}),
    (Milestone, {"event": "shipped v1"}),
    (Decision, {"what": "use Pydantic"}),
    (Episode, {"id": "e1", "started": NOW}),
]


@pytest.mark.parametrize("schema", SCHEMA_NO_ARGS, ids=lambda s: s.__name__)
def test_schema_default_roundtrip(schema, tmp_path):
    """Models with all defaults survive save → load."""
    model = schema()
    path = tmp_path / "test.json"
    save_validated(path, model)
    loaded = load_validated(path, schema)
    assert loaded.model_dump() == model.model_dump()


@pytest.mark.parametrize("schema,kwargs", SCHEMA_WITH_ARGS, ids=[s.__name__ for s, _ in SCHEMA_WITH_ARGS])
def test_schema_required_roundtrip(schema, kwargs, tmp_path):
    """Models with required fields survive save → load."""
    model = schema(**kwargs)
    path = tmp_path / "test.json"
    save_validated(path, model)
    loaded = load_validated(path, schema)
    assert loaded.model_dump() == model.model_dump()


def test_mood_vector_values():
    m = MoodVector(valence=0.8, energy=0.3, openness=0.9)
    assert m.valence == 0.8
    assert m.energy == 0.3
    assert m.openness == 0.9


def test_imprint_with_data(tmp_path):
    imp = Imprint(feeling="warm connection", strength=0.8, created=datetime.now().isoformat())
    path = tmp_path / "imprint.json"
    save_validated(path, imp)
    loaded = load_validated(path, Imprint)
    assert loaded.feeling == "warm connection"
    assert loaded.strength == 0.8


def test_idea_score_bounds():
    """IdeaScore should enforce 0-5 range."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        IdeaScore(problem=6, market=3, effort=3, monetization=3, fit=3)
    with pytest.raises(Exception):
        IdeaScore(problem=-1)
    # Valid score
    s = IdeaScore(problem=5, market=4, effort=3, monetization=2, fit=1, total=15)
    assert s.problem == 5
    assert s.total == 15


def test_extra_fields_allowed():
    """extra='allow' should accept unknown fields without error."""
    data = {"valence": 0.5, "energy": 0.5, "openness": 0.5, "future_field": "hello"}
    m = MoodVector.model_validate(data)
    assert m.valence == 0.5
    dumped = m.model_dump()
    assert dumped["future_field"] == "hello"


def test_correction_full(tmp_path):
    c = Correction(
        id=1, mistake="forgot tests", correction="always run tests",
        context="after refactor", correction_type="tendency",
        fails_when="rushing", fine_when="quick fix",
        date="2026-01-01",
    )
    path = tmp_path / "corr.json"
    save_validated(path, c)
    loaded = load_validated(path, Correction)
    assert loaded.mistake == "forgot tests"
    assert loaded.fails_when == "rushing"


def test_reasoning_trail_roundtrip(tmp_path):
    h = Hypothesis(h="Maybe it's a race condition", evidence=["log shows overlap"], confidence=0.7)
    trail = ReasoningTrail(
        trail_id="t1", started="2026-01-01T00:00:00", context="flaky test",
        hypotheses=[h.model_dump()],
        status="active", tags=["debug"],
    )
    path = tmp_path / "trail.json"
    save_validated(path, trail)
    loaded = load_validated(path, ReasoningTrail)
    assert loaded.trail_id == "t1"
    assert len(loaded.hypotheses) == 1
    assert loaded.hypotheses[0].h == "Maybe it's a race condition"


# ============================================================================
# List round-trip
# ============================================================================

def test_list_roundtrip(tmp_path):
    goals = [
        Goal(id=1, title="Ship v1", status="active", priority="high", created="2026-01-01", last_touched="2026-01-01"),
        Goal(id=2, title="Add tests", status="active", priority="medium", created="2026-01-01", last_touched="2026-01-01"),
    ]
    path = tmp_path / "goals.json"
    save_validated_list(path, goals)
    loaded = load_validated_list(path, Goal)
    assert len(loaded) == 2
    assert loaded[0].title == "Ship v1"
    assert loaded[1].id == 2


def test_list_load_empty(tmp_path):
    path = tmp_path / "missing.json"
    loaded = load_validated_list(path, Goal)
    assert loaded == []


def test_list_load_corrupt(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json at all {{{")
    loaded = load_validated_list(path, Goal)
    assert loaded == []


# ============================================================================
# Atomic write
# ============================================================================

def test_atomic_write_json(tmp_path):
    data = {"key": "value", "nested": {"a": 1}}
    path = tmp_path / "atomic.json"
    atomic_write_json(path, data)
    loaded = json.loads(path.read_text())
    assert loaded == data


def test_atomic_write_no_tmp_leftover(tmp_path):
    path = tmp_path / "clean.json"
    atomic_write_json(path, {"x": 1})
    tmp_file = path.with_suffix(".json.tmp")
    assert not tmp_file.exists()


def test_atomic_write_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "file.json"
    atomic_write_json(path, {"ok": True})
    assert path.exists()
    assert json.loads(path.read_text()) == {"ok": True}


# ============================================================================
# Exceptions
# ============================================================================

def test_exceptions_are_catchable():
    with pytest.raises(ElaraNotFoundError):
        raise ElaraNotFoundError("thing not found")
    with pytest.raises(ElaraValidationError):
        raise ElaraValidationError("bad input")

def test_exceptions_inherit_from_exception():
    assert issubclass(ElaraNotFoundError, Exception)
    assert issubclass(ElaraValidationError, Exception)
