"""Tier 2: Decay math tests — mood, imprints, temperament."""

import math
import random
import pytest
from datetime import datetime, timedelta

from daemon.state_core import (
    _apply_time_decay, _decay_imprints,
    TEMPERAMENT, DECAY_RATE, RESIDUE_DECAY_RATE, NOISE_SCALE,
)


def _make_state(mood_v=0.9, mood_e=0.9, mood_o=0.9, hours_ago=1.0, imprints=None, load=0):
    """Helper to create a state dict with last_update set N hours ago."""
    return {
        "mood": {"valence": mood_v, "energy": mood_e, "openness": mood_o},
        "temperament": TEMPERAMENT.copy(),
        "last_update": (datetime.now() - timedelta(hours=hours_ago)).isoformat(),
        "imprints": imprints or [],
        "allostatic_load": load,
    }


# ============================================================================
# Mood decay basics
# ============================================================================

class TestMoodDecay:

    def test_mood_decays_toward_baseline(self):
        """High mood should decay toward temperament baseline."""
        random.seed(42)  # Deterministic noise
        state = _make_state(mood_v=0.9, hours_ago=2.0)
        result = _apply_time_decay(state)
        # Valence baseline is 0.55. After decay, should be closer.
        assert result["mood"]["valence"] < 0.9
        assert result["mood"]["valence"] > 0.55  # Not past baseline

    def test_low_mood_decays_up(self):
        """Low mood should decay up toward baseline."""
        random.seed(42)
        state = _make_state(mood_v=0.1, hours_ago=2.0)
        result = _apply_time_decay(state)
        assert result["mood"]["valence"] > 0.1

    def test_no_decay_without_last_update(self):
        state = {"mood": {"valence": 0.9, "energy": 0.5, "openness": 0.5}}
        result = _apply_time_decay(state)
        assert result["mood"]["valence"] == 0.9

    def test_no_decay_for_tiny_interval(self):
        """Less than 0.01 hours (~36 seconds) should not decay."""
        state = _make_state(mood_v=0.9, hours_ago=0.005)
        result = _apply_time_decay(state)
        assert result["mood"]["valence"] == 0.9

    def test_valence_clamped_to_range(self):
        """Valence should stay in [-1, 1]."""
        random.seed(0)
        state = _make_state(mood_v=-0.95, hours_ago=0.5)
        state["temperament"]["valence"] = -0.5
        result = _apply_time_decay(state)
        assert result["mood"]["valence"] >= -1
        assert result["mood"]["valence"] <= 1

    def test_energy_openness_clamped_to_01(self):
        """Energy and openness should stay in [0, 1]."""
        random.seed(0)
        state = _make_state(mood_e=0.01, mood_o=0.99, hours_ago=1.0)
        result = _apply_time_decay(state)
        assert 0 <= result["mood"]["energy"] <= 1
        assert 0 <= result["mood"]["openness"] <= 1


# ============================================================================
# Decay time cap (clock jump protection)
# ============================================================================

class TestDecayTimeCap:

    def test_100h_same_as_24h(self):
        """100 hours ago should produce same decay as 24 hours (capped)."""
        random.seed(42)
        state_100 = _make_state(mood_v=0.9, hours_ago=100)
        result_100 = _apply_time_decay(state_100)

        random.seed(42)
        state_24 = _make_state(mood_v=0.9, hours_ago=24)
        result_24 = _apply_time_decay(state_24)

        assert abs(result_100["mood"]["valence"] - result_24["mood"]["valence"]) < 0.001

    def test_1000h_does_not_zero_out(self):
        """Even extreme clock jump shouldn't zero out mood."""
        random.seed(42)
        state = _make_state(mood_v=0.9, hours_ago=1000)
        result = _apply_time_decay(state)
        # With 24h cap and baseline 0.55, should not go below ~0.55
        assert result["mood"]["valence"] > 0.5


# ============================================================================
# Allostatic load
# ============================================================================

class TestAllostatic:

    def test_load_suppresses_baseline(self):
        """High allostatic load should make energy decay toward lower target."""
        random.seed(42)
        state_no_load = _make_state(mood_e=0.9, hours_ago=4, load=0)
        result_no_load = _apply_time_decay(state_no_load)

        random.seed(42)
        state_high_load = _make_state(mood_e=0.9, hours_ago=4, load=1.0)
        result_high_load = _apply_time_decay(state_high_load)

        # High load → energy decays further (lower effective baseline)
        assert result_high_load["mood"]["energy"] < result_no_load["mood"]["energy"]

    def test_load_recovers_over_time(self):
        state = _make_state(hours_ago=5, load=0.5)
        result = _apply_time_decay(state)
        assert result["allostatic_load"] < 0.5
        assert result["allostatic_load"] >= 0


# ============================================================================
# Imprint decay
# ============================================================================

class TestImprints:

    def test_imprint_decays(self):
        imprints = [{"feeling": "warm", "strength": 0.8, "type": "moment"}]
        result = _decay_imprints(imprints, hours=5)
        assert len(result) == 1
        assert result[0]["strength"] < 0.8

    def test_weak_imprint_archived(self):
        """Imprint below threshold should be removed."""
        imprints = [{"feeling": "faint", "strength": 0.11, "type": "moment"}]
        result = _decay_imprints(imprints, hours=10)
        assert len(result) == 0

    def test_connection_decays_slower(self):
        """Connection type should decay at 0.5x rate."""
        moment = [{"feeling": "a", "strength": 0.5, "type": "moment"}]
        connection = [{"feeling": "b", "strength": 0.5, "type": "connection"}]
        r_moment = _decay_imprints(moment, hours=5)
        r_connection = _decay_imprints(connection, hours=5)
        # Connection should retain more strength
        assert r_connection[0]["strength"] > r_moment[0]["strength"]

    def test_connection_lower_archive_threshold(self):
        """Connection imprints survive at lower strength than moments."""
        # 0.06 — below moment threshold (0.1) but above connection threshold (0.05)
        connection = [{"feeling": "bond", "strength": 0.06, "type": "connection"}]
        moment = [{"feeling": "flash", "strength": 0.06, "type": "moment"}]
        # Minimal decay
        r_conn = _decay_imprints(connection, hours=0.01)
        r_moment = _decay_imprints(moment, hours=0.01)
        assert len(r_conn) == 1  # Connection survives at 0.06
        assert len(r_moment) == 0  # Moment dies below 0.1

    def test_empty_imprints(self):
        assert _decay_imprints([], hours=10) == []
