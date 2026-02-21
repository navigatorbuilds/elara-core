# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for the Unified Decision Registry (UDR)."""

import pytest
from pathlib import Path

from core.paths import configure, reset
from daemon.udr import DecisionRegistry, reset_registry


@pytest.fixture(autouse=True)
def udr_env(tmp_path):
    """Configure paths to use temp dir, reset singletons."""
    configure(tmp_path)
    reset_registry()
    yield tmp_path
    reset_registry()
    reset()


@pytest.fixture
def reg(udr_env):
    """Fresh DecisionRegistry instance."""
    return DecisionRegistry()


# ---------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------

class TestRecordAndCheck:
    def test_record_creates_entry(self, reg):
        result = reg.record_decision(
            domain="upload", entity="arxiv",
            reason="endorsement blocked", confidence=0.9,
        )
        assert result["action_signature"] == "upload:arxiv"
        assert result["verdict"] == "rejected"
        assert result["confidence"] == 0.9

    def test_check_finds_existing(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="blocked")
        found = reg.check_decision("upload", "arxiv")
        assert found is not None
        assert found["verdict"] == "rejected"

    def test_check_returns_none_for_missing(self, reg):
        assert reg.check_decision("upload", "nonexistent") is None


class TestUpsert:
    def test_upsert_bumps_confidence(self, reg):
        reg.record_decision(domain="upload", entity="arxiv",
                            reason="first", confidence=0.8)
        reg.record_decision(domain="upload", entity="arxiv",
                            reason="second", confidence=0.8)
        result = reg.check_decision("upload", "arxiv")
        assert result["confidence"] == 0.9  # 0.8 + 0.1
        assert result["reason"] == "second"

    def test_upsert_caps_at_one(self, reg):
        reg.record_decision(domain="x", entity="y", confidence=0.95)
        reg.record_decision(domain="x", entity="y", confidence=0.95)
        result = reg.check_decision("x", "y")
        assert result["confidence"] == 1.0


# ---------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------

class TestNormalization:
    def test_case_insensitive(self, reg):
        reg.record_decision(domain="Upload", entity="ArXiv", reason="test")
        assert reg.check_decision("upload", "arxiv") is not None

    def test_whitespace_normalized(self, reg):
        reg.record_decision(domain="  upload  ", entity="  arxiv  ", reason="test")
        assert reg.check_decision("upload", "arxiv") is not None


# ---------------------------------------------------------------
# Quick check (in-memory)
# ---------------------------------------------------------------

class TestQuickCheck:
    def test_quick_check_after_record(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="blocked")
        assert reg.quick_check("upload", "arxiv") is True

    def test_quick_check_false_for_missing(self, reg):
        assert reg.quick_check("upload", "arxiv") is False

    def test_quick_check_false_for_approved(self, reg):
        reg.record_decision(domain="tool", entity="redis",
                            verdict="approved", reason="works great")
        assert reg.quick_check("tool", "redis") is False


# ---------------------------------------------------------------
# Entity scan (check_entities)
# ---------------------------------------------------------------

class TestCheckEntities:
    def test_finds_entity_in_text(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="blocked")
        matches = reg.check_entities("should we try uploading to arxiv?")
        assert len(matches) == 1
        assert matches[0]["entity"] == "arxiv"

    def test_returns_empty_for_no_match(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="blocked")
        matches = reg.check_entities("let's build a new feature")
        assert len(matches) == 0

    def test_max_two_hits(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="a")
        reg.record_decision(domain="upload", entity="techrxiv", reason="b")
        reg.record_decision(domain="outreach", entity="professors", reason="c")
        matches = reg.check_entities("arxiv techrxiv professors")
        assert len(matches) <= 2


# ---------------------------------------------------------------
# List and stats
# ---------------------------------------------------------------

class TestListAndStats:
    def test_list_all(self, reg):
        reg.record_decision(domain="a", entity="b", reason="r1")
        reg.record_decision(domain="c", entity="d", reason="r2")
        results = reg.list_decisions()
        assert len(results) == 2

    def test_list_filtered_by_domain(self, reg):
        reg.record_decision(domain="upload", entity="a", reason="r1")
        reg.record_decision(domain="outreach", entity="b", reason="r2")
        results = reg.list_decisions(domain="upload")
        assert len(results) == 1

    def test_stats_counts(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="r")
        reg.record_decision(domain="upload", entity="techrxiv",
                            verdict="failed", reason="r")
        s = reg.stats()
        assert s["total_decisions"] == 2
        assert s["by_domain"]["upload"] == 2
        assert "rejected" in s["by_verdict"]


# ---------------------------------------------------------------
# Boot
# ---------------------------------------------------------------

class TestBoot:
    def test_boot_loads_entity_set(self, reg):
        reg.record_decision(domain="upload", entity="arxiv", reason="blocked")
        reg.record_decision(domain="tool", entity="redis",
                            verdict="approved", reason="ok")
        # Create a fresh registry to simulate boot
        reg2 = DecisionRegistry()
        summary = reg2.boot_decisions()
        assert "1 blocked entities" in summary
        assert reg2.quick_check("upload", "arxiv") is True
        assert reg2.quick_check("tool", "redis") is False


# ---------------------------------------------------------------
# DB file location
# ---------------------------------------------------------------

class TestPaths:
    def test_db_created_in_data_dir(self, reg, udr_env):
        reg.record_decision(domain="test", entity="x", reason="r")
        assert (udr_env / "elara-udr.db").exists()
