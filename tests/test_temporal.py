# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for long-range memory: temporal sweep, landmarks, timeline."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ── temporal.py tests ──────────────────────────────────────────


class TestTemporalSweep:
    """Test temporal_sweep and helpers."""

    def test_time_windows_defined(self):
        from memory.temporal import TIME_WINDOWS
        assert len(TIME_WINDOWS) == 4
        # Each window: (label, start_days, end_days, max_results)
        for label, start, end, max_n in TIME_WINDOWS:
            assert isinstance(label, str)
            assert start < end
            assert max_n >= 1

    def test_landmark_threshold(self):
        from memory.temporal import LANDMARK_THRESHOLD
        assert LANDMARK_THRESHOLD == 0.9

    def test_format_temporal_digest_empty(self):
        from memory.temporal import format_temporal_digest
        assert format_temporal_digest([]) == ""

    def test_format_temporal_digest_landmarks(self):
        from memory.temporal import format_temporal_digest
        items = [
            {"content": "Patent filed", "source": "landmark", "date": "2026-02-14", "importance": 1.0},
        ]
        result = format_temporal_digest(items)
        assert "[LANDMARK]" in result
        assert "Patent filed" in result

    def test_format_temporal_digest_memories(self):
        from memory.temporal import format_temporal_digest
        items = [
            {"content": "Built Layer 2 stub", "source": "memory", "date": "2026-01-15", "importance": 0.7},
            {"content": "Shipped v0.10.0", "source": "milestone", "date": "2026-01-20", "importance": 0.8},
        ]
        result = format_temporal_digest(items)
        assert "[2026-01-15] [R]" in result
        assert "[2026-01-20] [M]" in result
        assert "Built Layer 2" in result
        assert "Shipped v0.10.0" in result

    def test_format_temporal_digest_mixed(self):
        from memory.temporal import format_temporal_digest
        items = [
            {"content": "Never forget this", "source": "landmark", "date": "2026-01-01", "importance": 0.95},
            {"content": "Old memory", "source": "memory", "date": "2025-12-15", "importance": 0.6},
        ]
        result = format_temporal_digest(items)
        # Landmarks section comes first
        lines = result.strip().split("\n")
        assert "[LANDMARK]" in lines[0]

    def test_boot_temporal_context_returns_string(self):
        from memory.temporal import boot_temporal_context
        # Should return empty string or formatted output (depends on ChromaDB state)
        result = boot_temporal_context()
        assert isinstance(result, str)

    def test_boot_temporal_context_header(self):
        from memory.temporal import boot_temporal_context, temporal_sweep, format_temporal_digest
        # If there are items, header should be present
        items = temporal_sweep()
        if items:
            result = boot_temporal_context()
            assert "[LONG-RANGE MEMORY]" in result

    @patch("memory.vector.get_memory")
    def test_recall_landmarks_filters_by_importance(self, mock_get_memory):
        from memory.temporal import recall_landmarks, LANDMARK_THRESHOLD

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["Important thing", "Also important"],
            "metadatas": [
                {"date": "2026-02-14", "importance": 0.95, "type": "decision"},
                {"date": "2026-01-10", "importance": 0.9, "type": "fact"},
            ],
        }
        mock_mem = MagicMock()
        mock_mem.collection = mock_collection
        mock_get_memory.return_value = mock_mem

        results = recall_landmarks()
        assert len(results) == 2
        # Should be sorted by importance descending
        assert results[0]["importance"] >= results[1]["importance"]
        # Verify the where filter was called with >= 0.9
        call_args = mock_collection.get.call_args
        assert call_args[1]["where"]["importance"]["$gte"] == LANDMARK_THRESHOLD

    @patch("memory.vector.get_memory")
    def test_recall_landmarks_empty_collection(self, mock_get_memory):
        from memory.temporal import recall_landmarks

        mock_collection = MagicMock()
        mock_collection.get.return_value = {"documents": [], "metadatas": []}
        mock_mem = MagicMock()
        mock_mem.collection = mock_collection
        mock_get_memory.return_value = mock_mem

        results = recall_landmarks()
        assert results == []

    def test_query_memories_in_window(self):
        from memory.temporal import _query_memories_in_window

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["Memory A", "Memory B", "Memory C"],
            "metadatas": [
                {"date": "2026-02-01", "importance": 0.8, "type": "fact"},
                {"date": "2026-02-03", "importance": 0.6, "type": "conversation"},
                {"date": "2026-02-05", "importance": 0.9, "type": "decision"},
            ],
        }
        mock_mem = MagicMock()
        mock_mem.collection = mock_collection

        results = _query_memories_in_window(mock_mem, 7, 14, 2, 0.5)
        # Should return top 2 by importance
        assert len(results) == 2
        assert results[0]["importance"] >= results[1]["importance"]

    def test_temporal_sweep_deduplicates(self):
        from memory.temporal import temporal_sweep
        # Run a sweep — results should have no duplicate content (first 80 chars)
        results = temporal_sweep()
        seen = set()
        for r in results:
            key = r.get("content", "")[:80]
            assert key not in seen, f"Duplicate found: {key}"
            seen.add(key)

    def test_temporal_sweep_sorted_chronologically(self):
        from memory.temporal import temporal_sweep
        results = temporal_sweep()
        dates = [r.get("date", "9999") for r in results]
        assert dates == sorted(dates), "Results should be sorted oldest-first"


class TestLandmarkTagging:
    """Test that vector memory tags landmarks correctly."""

    @patch("memory.vector.CHROMA_AVAILABLE", True)
    def test_remember_sets_landmark_flag(self):
        from memory.vector import VectorMemory

        mem = VectorMemory()
        if mem.collection is None:
            pytest.skip("ChromaDB not available")

        # Remember with high importance
        memory_id = mem.remember("This is a landmark", importance=0.95)
        assert memory_id != "memory_disabled"

        # Verify the stored metadata has landmark=True
        result = mem.collection.get(ids=[memory_id], include=["metadatas"])
        if result["metadatas"]:
            meta = result["metadatas"][0]
            assert meta.get("landmark") is True
            assert meta.get("importance") == 0.95

        # Clean up
        mem.forget(memory_id)

    @patch("memory.vector.CHROMA_AVAILABLE", True)
    def test_remember_no_landmark_below_threshold(self):
        from memory.vector import VectorMemory

        mem = VectorMemory()
        if mem.collection is None:
            pytest.skip("ChromaDB not available")

        memory_id = mem.remember("Normal memory", importance=0.5)
        assert memory_id != "memory_disabled"

        result = mem.collection.get(ids=[memory_id], include=["metadatas"])
        if result["metadatas"]:
            meta = result["metadatas"][0]
            assert "landmark" not in meta or meta.get("landmark") is not True

        mem.forget(memory_id)


class TestTimeline:
    """Test the timeline action in episode_query."""

    def test_build_timeline_no_collection(self):
        from elara_mcp.tools.episodes import _build_timeline

        mock_episodic = MagicMock()
        mock_episodic.milestones_collection = None

        result = _build_timeline(mock_episodic)
        assert "No milestones indexed" in result

    def test_build_timeline_empty(self):
        from elara_mcp.tools.episodes import _build_timeline

        mock_episodic = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"documents": [], "metadatas": []}
        mock_episodic.milestones_collection = mock_collection

        result = _build_timeline(mock_episodic)
        assert "No milestones found" in result

    def test_build_timeline_grouped_by_month(self):
        from elara_mcp.tools.episodes import _build_timeline

        mock_episodic = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": [
                "Shipped v0.10.0",
                "Added Layer 2 network",
                "Filed patent",
            ],
            "metadatas": [
                {"timestamp": "2026-01-15T10:00:00", "importance": 0.8, "type": "milestone", "project": "elara-core"},
                {"timestamp": "2026-01-28T14:00:00", "importance": 0.7, "type": "milestone", "project": "elara-core"},
                {"timestamp": "2026-02-14T09:00:00", "importance": 0.9, "type": "decision", "project": ""},
            ],
        }
        mock_episodic.milestones_collection = mock_collection

        result = _build_timeline(mock_episodic)
        assert "Timeline" in result
        assert "2026-01" in result
        assert "2026-02" in result
        assert "Shipped v0.10.0" in result
        assert "Filed patent" in result

    def test_build_timeline_sorted_by_importance(self):
        from elara_mcp.tools.episodes import _build_timeline

        mock_episodic = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["Low importance", "High importance", "Medium importance"],
            "metadatas": [
                {"timestamp": "2026-01-01T00:00:00", "importance": 0.3, "type": "milestone", "project": ""},
                {"timestamp": "2026-01-01T00:00:00", "importance": 0.9, "type": "milestone", "project": ""},
                {"timestamp": "2026-01-01T00:00:00", "importance": 0.6, "type": "milestone", "project": ""},
            ],
        }
        mock_episodic.milestones_collection = mock_collection

        # With n=2, should only show top 2 by importance
        result = _build_timeline(mock_episodic, n=2)
        assert "High importance" in result
        assert "Medium importance" in result
        assert "Low importance" not in result

    def test_build_timeline_key_marker(self):
        from elara_mcp.tools.episodes import _build_timeline

        mock_episodic = MagicMock()
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["Key event", "Normal event"],
            "metadatas": [
                {"timestamp": "2026-01-01T00:00:00", "importance": 0.8, "type": "milestone", "project": ""},
                {"timestamp": "2026-01-01T00:00:00", "importance": 0.4, "type": "milestone", "project": ""},
            ],
        }
        mock_episodic.milestones_collection = mock_collection

        result = _build_timeline(mock_episodic)
        # importance >= 0.7 gets * marker, below gets -
        assert "* Key event" in result
        assert "- Normal event" in result
