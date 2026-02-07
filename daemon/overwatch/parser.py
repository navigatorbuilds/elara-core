"""
Overwatch parser — text extraction, JSONL reading, exchange parsing.
"""

import logging
import json
from pathlib import Path
from typing import Optional, List, Dict

from daemon.overwatch.config import SYSTEM_REMINDER_RE, log


logger = logging.getLogger("elara.overwatch.parser")

class ParserMixin:
    """Mixin for JSONL parsing and exchange extraction."""

    def _clean_text(self, text: str) -> str:
        """Strip system-reminder blocks."""
        text = SYSTEM_REMINDER_RE.sub('', text)
        return text.strip()

    def _extract_text(self, entry: dict) -> Optional[str]:
        """Extract readable text from a JSONL entry.

        Handles two content formats:
        - content=str: direct user messages (e.g. "test3", "ok go")
        - content=list: blocks array — only extracts from type="text" blocks
          (thinking, tool_use, tool_result blocks are ignored)
        """
        msg = entry.get("message", {})
        content = msg.get("content", "")

        if isinstance(content, str):
            text = self._clean_text(content)
            return text if text and len(text) > 1 else None

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned and len(cleaned) > 1:
                        texts.append(cleaned)
            return "\n".join(texts) if texts else None

        return None

    def _read_new_lines(self, jsonl_path: Path) -> List[dict]:
        """Read new lines from the JSONL since last position."""
        entries = []
        try:
            file_size = jsonl_path.stat().st_size
            if file_size < self.last_position:
                log.warning("JSONL truncated (%d < %d), resetting position", file_size, self.last_position)
                self.last_position = 0
            if file_size <= self.last_position:
                return []

            with open(jsonl_path, 'r') as f:
                f.seek(self.last_position)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if not entry.get("isSidechain"):
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
                self.last_position = f.tell()
        except (OSError, IOError) as e:
            log.error(f"Read error: {e}")

        return entries

    def _parse_exchanges(self, entries: List[dict]) -> List[Dict[str, str]]:
        """Parse JSONL entries into user+assistant exchange pairs.

        State persists across calls via self._pending_user and self._assistant_texts,
        because user and assistant entries often arrive in different poll cycles.
        """
        exchanges = []

        for entry in entries:
            entry_type = entry.get("type")

            if entry_type == "user":
                text = self._extract_text(entry)
                if text:
                    log.debug(f"User text extracted ({len(text)} chars): {text[:60]}")
                if not text or text.startswith("<") or text.startswith("{"):
                    continue

                # Real user message — flush any accumulated exchange first
                if self._pending_user and self._assistant_texts:
                    exchanges.append({
                        "user_text": self._pending_user["user_text"],
                        "assistant_text": " ".join(self._assistant_texts),
                        "timestamp": self._pending_user["timestamp"],
                    })

                self._pending_user = {
                    "user_text": text,
                    "timestamp": entry.get("timestamp", ""),
                }
                self._assistant_texts = []

            elif entry_type == "assistant" and self._pending_user:
                text = self._extract_text(entry)
                if text:
                    self._assistant_texts.append(text)

        return exchanges
