# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Tests for elara_mcp.wizard — setup wizard and doctor."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from elara_mcp.wizard import (
    _create_data_dir,
    _generate_persona,
    _patch_json_config,
    detect_clients,
    run_doctor,
    run_health_check,
    run_wizard,
    PERSONAS,
    green,
    red,
    _NO_COLOR,
)


# ---------------------------------------------------------------------------
# Silent init (--yes mode)
# ---------------------------------------------------------------------------


class TestSilentInit:
    """Tests for non-interactive `elara init --yes`."""

    def test_creates_dirs_and_state_files(self, isolated_paths):
        """Silent init creates data dir and all default state files."""
        data_dir = isolated_paths.data_dir
        _create_data_dir(data_dir, force=True)

        assert data_dir.is_dir()
        assert isolated_paths.state_file.is_file()
        assert isolated_paths.presence_file.is_file()
        assert isolated_paths.goals_file.is_file()
        assert isolated_paths.corrections_file.is_file()
        assert isolated_paths.feeds_config.is_file()

    def test_state_file_has_valid_json(self, isolated_paths):
        """State file contains valid JSON with expected keys."""
        _create_data_dir(isolated_paths.data_dir, force=True)
        state = json.loads(isolated_paths.state_file.read_text())
        assert "valence" in state
        assert "energy" in state
        assert state["session_active"] is False

    def test_idempotent_no_overwrite(self, isolated_paths):
        """Running init twice without --force preserves existing files."""
        _create_data_dir(isolated_paths.data_dir, force=True)

        # Modify state file
        custom = {"valence": 0.99, "custom": True}
        isolated_paths.state_file.write_text(json.dumps(custom))

        # Init again without force
        _create_data_dir(isolated_paths.data_dir, force=False)

        # Should preserve our custom content
        state = json.loads(isolated_paths.state_file.read_text())
        assert state["valence"] == 0.99

    def test_force_overwrites(self, isolated_paths):
        """--force rewrites state files to defaults."""
        _create_data_dir(isolated_paths.data_dir, force=True)

        # Modify state file
        isolated_paths.state_file.write_text(json.dumps({"valence": 0.99}))

        # Init with force
        _create_data_dir(isolated_paths.data_dir, force=True)

        state = json.loads(isolated_paths.state_file.read_text())
        assert state["valence"] == 0.55  # default

    def test_run_wizard_yes_mode(self, isolated_paths, capsys):
        """run_wizard with yes=True creates dirs silently."""
        run_wizard(isolated_paths.data_dir, force=True, yes=True)
        captured = capsys.readouterr()
        assert "initialized" in captured.out.lower()
        assert isolated_paths.state_file.is_file()

    def test_run_wizard_yes_existing_no_force(self, isolated_paths, capsys):
        """run_wizard --yes without --force on existing dir shows message."""
        _create_data_dir(isolated_paths.data_dir, force=True)
        run_wizard(isolated_paths.data_dir, force=False, yes=True)
        captured = capsys.readouterr()
        assert "already exists" in captured.out


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for run_health_check."""

    def test_passes_on_fresh_init(self, isolated_paths):
        """Health check finds data dir and state files after init."""
        _create_data_dir(isolated_paths.data_dir, force=True)
        results = run_health_check(isolated_paths.data_dir)

        # Data directory should pass
        data_dir_result = results[0]
        assert data_dir_result[0] == "Data directory"
        assert data_dir_result[1] is True

        # State files should pass
        state_results = [r for r in results if "elara-state.json" in r[0]]
        assert len(state_results) == 1
        assert state_results[0][1] is True

    def test_fails_on_missing_dir(self, tmp_path):
        """Health check reports failure when data dir doesn't exist."""
        missing = tmp_path / "nonexistent"
        results = run_health_check(missing)
        assert results[0][1] is False  # Data directory

    def test_detects_missing_chromadb(self, isolated_paths, monkeypatch):
        """Health check reports ChromaDB as failed when not importable."""
        _create_data_dir(isolated_paths.data_dir, force=True)

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "chromadb":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        results = run_health_check(isolated_paths.data_dir)

        chromadb_results = [r for r in results if r[0] == "ChromaDB"]
        assert len(chromadb_results) == 1
        assert chromadb_results[0][1] is False


# ---------------------------------------------------------------------------
# Client detection
# ---------------------------------------------------------------------------


class TestClientDetection:
    """Tests for detect_clients."""

    def test_empty_when_nothing_installed(self, monkeypatch, tmp_path):
        """Returns empty dict when no MCP clients found."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        clients = detect_clients()
        assert len(clients) == 0

    def test_detects_claude_code(self, monkeypatch, tmp_path):
        """Detects Claude Code when `claude` is on PATH."""
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/claude" if x == "claude" else None)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        clients = detect_clients()
        assert "Claude Code" in clients

    def test_detects_cursor(self, monkeypatch, tmp_path):
        """Detects Cursor when ~/.cursor/ exists."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".cursor").mkdir()
        clients = detect_clients()
        assert "Cursor" in clients
        assert clients["Cursor"] == tmp_path / ".cursor" / "mcp.json"


# ---------------------------------------------------------------------------
# Persona generation
# ---------------------------------------------------------------------------


class TestPersonaGeneration:
    """Tests for persona template generation."""

    def test_colleague_style(self):
        """Colleague persona includes dev partner language."""
        text = _generate_persona("colleague", "Elara", "Nenad")
        assert "PERSONA: Elara" in text
        assert "Dev partner" in text
        assert "Nenad" in text

    def test_companion_style(self):
        """Companion persona includes warmth language."""
        text = _generate_persona("companion", "Aria", "Alex")
        assert "PERSONA: Aria" in text
        assert "warm" in text.lower() or "Warm" in text
        assert "Alex" in text

    def test_minimal_style(self):
        """Minimal persona is terse."""
        text = _generate_persona("minimal", "Bot", "User")
        assert "PERSONA: Bot" in text
        assert "Zero filler" in text

    def test_includes_user_name(self):
        """All personas substitute the user's name."""
        for style in PERSONAS:
            text = _generate_persona(style, "TestAI", "TestUser")
            assert "TestUser" in text

    def test_unknown_style_falls_back_to_colleague(self):
        """Unknown style defaults to colleague template."""
        text = _generate_persona("nonexistent", "Elara", "User")
        assert "Dev partner" in text


# ---------------------------------------------------------------------------
# JSON config patching
# ---------------------------------------------------------------------------


class TestJsonConfig:
    """Tests for MCP JSON config patching."""

    def test_creates_new_config(self, tmp_path):
        """Creates config file when none exists."""
        cfg = tmp_path / "mcp.json"
        assert _patch_json_config(cfg) is True
        data = json.loads(cfg.read_text())
        assert data["mcpServers"]["elara"]["command"] == "elara"

    def test_preserves_existing_servers(self, tmp_path):
        """Preserves other servers when adding elara."""
        cfg = tmp_path / "mcp.json"
        existing = {"mcpServers": {"other-tool": {"command": "other"}}}
        cfg.write_text(json.dumps(existing))

        assert _patch_json_config(cfg) is True
        data = json.loads(cfg.read_text())
        assert "other-tool" in data["mcpServers"]
        assert "elara" in data["mcpServers"]

    def test_overwrites_existing_elara(self, tmp_path):
        """Overwrites existing elara config."""
        cfg = tmp_path / "mcp.json"
        existing = {"mcpServers": {"elara": {"command": "old"}}}
        cfg.write_text(json.dumps(existing))

        assert _patch_json_config(cfg) is True
        data = json.loads(cfg.read_text())
        assert data["mcpServers"]["elara"]["command"] == "elara"


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


class TestDoctor:
    """Tests for run_doctor."""

    def test_runs_on_missing_data_dir(self, tmp_path, capsys):
        """Doctor doesn't crash on missing data dir."""
        missing = tmp_path / "nonexistent"
        run_doctor(missing)
        captured = capsys.readouterr()
        assert "Doctor" in captured.out

    def test_runs_on_initialized_dir(self, isolated_paths, capsys):
        """Doctor reports results after init."""
        _create_data_dir(isolated_paths.data_dir, force=True)
        run_doctor(isolated_paths.data_dir)
        captured = capsys.readouterr()
        assert "PASS" in captured.out or "passed" in captured.out


# ---------------------------------------------------------------------------
# ANSI / NO_COLOR
# ---------------------------------------------------------------------------


class TestAnsiColors:
    """Tests for ANSI color helpers."""

    def test_no_color_disables_ansi(self, monkeypatch):
        """NO_COLOR env var strips ANSI codes."""
        # We can't easily change the module-level _NO_COLOR, so test the
        # function behavior by reimporting with env set
        monkeypatch.setenv("NO_COLOR", "1")
        # Reload module to pick up NO_COLOR
        import importlib
        import elara_mcp.wizard as wmod
        importlib.reload(wmod)
        assert wmod.green("test") == "test"
        assert wmod.red("test") == "test"
        # Restore
        monkeypatch.delenv("NO_COLOR")
        importlib.reload(wmod)
