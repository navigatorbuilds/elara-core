"""
Overwatch snapshot — session state snapshots for boot continuity.
"""

import json
import time
from datetime import datetime
from typing import Dict

from daemon.overwatch.config import (
    SNAPSHOT_PATH, SNAPSHOT_INTERVAL, SNAPSHOT_MIN_EXCHANGES, log,
)
from daemon.schemas import atomic_write_json


class SnapshotMixin:
    """Mixin for session snapshots."""

    def _build_snapshot(self) -> None:
        """Build a session snapshot — one file, always overwritten.

        Fields for boot:
        - continuation: last user message (for quick reboots)
        - greeting_hint: exchange count (for fresh sessions)
        - last_exchanges: raw transcript of last 5 exchanges
        """
        if not self.recent_exchanges:
            return

        recent = self.recent_exchanges[-5:]

        raw_exchanges = []
        for ex in recent:
            raw_exchanges.append({
                "user": ex["user_text"][:300],
                "assistant": ex["assistant_text"][:300],
            })

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.current_session_id,
            "exchange_count": self.exchange_counter,
            "continuation": self._fallback_continuation(),
            "greeting_hint": self._fallback_greeting(),
            "last_exchanges": raw_exchanges,
        }

        try:
            atomic_write_json(SNAPSHOT_PATH, snapshot)
            log.info(f"Snapshot written ({self.exchange_counter} exchanges)")
        except OSError as e:
            log.error(f"Snapshot write error: {e}")

    def _fallback_continuation(self) -> str:
        if self.recent_exchanges:
            last = self.recent_exchanges[-1]
            return f"Last: {last['user_text'][:100]}"
        return ""

    def _fallback_greeting(self) -> str:
        return f"Session had {self.exchange_counter} exchanges."

    def _check_snapshot(self) -> None:
        """Check if it's time to write a snapshot."""
        now = time.time()
        if (self.exchange_counter >= SNAPSHOT_MIN_EXCHANGES
                and now - self.last_snapshot_time > SNAPSHOT_INTERVAL):
            self._build_snapshot()
            self.last_snapshot_time = now
