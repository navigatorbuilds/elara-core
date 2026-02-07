"""Tier 4: Overwatch parser edge cases — JSONL handling, text cleaning."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from daemon.overwatch.parser import ParserMixin


class MockOverwatch(ParserMixin):
    """Minimal Overwatch mock with parser mixin."""

    def __init__(self):
        self.last_position = 0
        self._pending_user = None
        self._assistant_texts = []


@pytest.fixture
def parser():
    return MockOverwatch()


# ============================================================================
# Text cleaning
# ============================================================================

class TestCleanText:

    def test_strips_system_reminders(self, parser):
        text = "Hello <system-reminder>secret stuff</system-reminder> world"
        assert parser._clean_text(text) == "Hello  world"

    def test_strips_overwatch_context(self, parser):
        text = "Response <overwatch-context>injected cross-ref</overwatch-context> here"
        assert parser._clean_text(text) == "Response  here"

    def test_strips_multiline_blocks(self, parser):
        text = "Start <system-reminder>\nline1\nline2\n</system-reminder> End"
        assert parser._clean_text(text) == "Start  End"

    def test_strips_both_types(self, parser):
        text = "<system-reminder>a</system-reminder> middle <overwatch-context>b</overwatch-context>"
        assert parser._clean_text(text) == "middle"

    def test_plain_text_unchanged(self, parser):
        assert parser._clean_text("hello world") == "hello world"


# ============================================================================
# JSONL reading
# ============================================================================

class TestReadNewLines:

    def test_reads_valid_jsonl(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"content": "hello"}}),
            json.dumps({"type": "assistant", "message": {"content": "hi"}}),
        ]
        f.write_text("\n".join(lines) + "\n")
        entries = parser._read_new_lines(f)
        assert len(entries) == 2

    def test_skips_corrupt_json(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"valid": true}\nnot json at all\n{"also": "valid"}\n')
        entries = parser._read_new_lines(f)
        assert len(entries) == 2

    def test_skips_empty_lines(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a": 1}\n\n\n{"b": 2}\n')
        entries = parser._read_new_lines(f)
        assert len(entries) == 2

    def test_skips_sidechain_entries(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"content": "real"}}),
            json.dumps({"type": "user", "message": {"content": "side"}, "isSidechain": True}),
        ]
        f.write_text("\n".join(lines) + "\n")
        entries = parser._read_new_lines(f)
        assert len(entries) == 1

    def test_resumes_from_last_position(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a": 1}\n')
        parser._read_new_lines(f)
        # Append more
        with open(f, 'a') as fh:
            fh.write('{"b": 2}\n')
        entries = parser._read_new_lines(f)
        assert len(entries) == 1
        assert entries[0]["b"] == 2

    def test_truncation_resets_position(self, parser, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a": 1}\n{"b": 2}\n{"c": 3}\n')
        parser._read_new_lines(f)  # Reads all, position at end
        assert parser.last_position > 0

        # Truncate file (new session)
        f.write_text('{"d": 4}\n')
        entries = parser._read_new_lines(f)
        assert len(entries) == 1
        assert entries[0]["d"] == 4

    def test_missing_file(self, parser, tmp_path):
        f = tmp_path / "nonexistent.jsonl"
        entries = parser._read_new_lines(f)
        assert entries == []


# ============================================================================
# Exchange parsing
# ============================================================================

class TestParseExchanges:

    def _user_entry(self, text, ts="2026-01-01T12:00:00"):
        return {"type": "user", "message": {"content": text}, "timestamp": ts}

    def _assistant_entry(self, text):
        return {"type": "assistant", "message": {"content": text}}

    def test_basic_exchange(self, parser):
        entries = [self._user_entry("hello"), self._assistant_entry("hi there")]
        # Need a second user message to flush the first exchange
        entries.append(self._user_entry("second"))
        exchanges = parser._parse_exchanges(entries)
        assert len(exchanges) == 1
        assert exchanges[0]["user_text"] == "hello"
        assert exchanges[0]["assistant_text"] == "hi there"

    def test_skips_xml_user_messages(self, parser):
        entries = [
            self._user_entry("<system-reminder>ignore</system-reminder>"),
            self._assistant_entry("response"),
        ]
        exchanges = parser._parse_exchanges(entries)
        assert len(exchanges) == 0

    def test_skips_json_user_messages(self, parser):
        entries = [
            self._user_entry('{"tool": "result"}'),
            self._assistant_entry("response"),
        ]
        exchanges = parser._parse_exchanges(entries)
        assert len(exchanges) == 0
