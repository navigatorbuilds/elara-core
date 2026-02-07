"""
Elara Overwatch — Live Memory Daemon

Tails the active Claude Code session JSONL in real-time,
searches ALL conversation history in ChromaDB for cross-references,
and injects relevant context via a hook file.

Split into mixins:
- ParserMixin (parser.py) — text extraction, JSONL reading, exchange parsing
- SearchMixin (search.py) — history search, events, LLM filtering, injection
- IngestMixin (ingest.py) — micro-ingestion, triage, synthesis
- SnapshotMixin (snapshot.py) — session snapshots for boot continuity
"""

import os
import json
import time
import signal
from pathlib import Path
from typing import Optional, List, Dict, Any

from memory.conversations import get_conversations, ConversationMemory
from daemon.overwatch.config import (
    PROJECTS_DIR, PID_PATH, INJECT_PATH, SESSION_STATE_PATH,
    POLL_INTERVAL, HEARTBEAT_TIMEOUT, log,
)
from daemon.overwatch.parser import ParserMixin
from daemon.overwatch.search import SearchMixin
from daemon.overwatch.ingest import IngestMixin
from daemon.overwatch.snapshot import SnapshotMixin


class Overwatch(ParserMixin, SearchMixin, IngestMixin, SnapshotMixin):
    def __init__(self):
        self.conv: ConversationMemory = get_conversations()
        self.last_position: int = 0
        self.current_session_id: str = ""
        self.current_jsonl: Optional[Path] = None
        self.cooldowns: Dict[str, float] = {}
        self.prev_user_text: str = ""
        self.running: bool = True
        self.injection_count: int = 0

        # Priority integration
        self.session_state: Dict[str, Any] = self._load_session_state()

        # Micro-ingestion tracking
        self.exchanges_since_ingest: int = 0
        self.last_ingest_time: float = time.time()
        self.pending_exchanges: List[Dict[str, str]] = []
        self.pending_exchanges_for_synthesis: List[Dict[str, str]] = []
        self.exchange_counter: int = 0

        # Cross-poll parsing state
        self._pending_user: Optional[Dict[str, str]] = None
        self._assistant_texts: List[str] = []

        # Session snapshot tracking
        self.last_snapshot_time: float = 0
        self.recent_exchanges: List[Dict[str, str]] = []

    def find_active_session(self) -> Optional[Path]:
        """Find the most recently modified JSONL file — that's the active session."""
        if not PROJECTS_DIR.exists():
            return None
        newest = None
        newest_mtime = 0
        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                mtime = jsonl_file.stat().st_mtime
                if mtime > newest_mtime:
                    newest = jsonl_file
                    newest_mtime = mtime
        return newest

    def _load_session_state(self) -> Dict[str, Any]:
        if SESSION_STATE_PATH.exists():
            try:
                return json.loads(SESSION_STATE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _process_exchange(self, exchange: Dict[str, str]):
        """Core logic: process one new exchange."""
        combined = exchange["user_text"] + " " + exchange["assistant_text"]

        # 1. Search history for cross-references
        results = self._search_history(combined, threshold=0.65)

        # 2. Detect events
        events = self._detect_events(exchange)
        event_results = self._search_for_events(events) if events else []

        # 3. Inject if anything found
        if results or event_results:
            self._write_inject(results, event_results)

        # 4. Queue for micro-ingestion + synthesis
        self.exchange_counter += 1
        exchange["exchange_index"] = self.exchange_counter
        self.pending_exchanges.append(exchange)
        self.pending_exchanges_for_synthesis.append(exchange)
        self.exchanges_since_ingest += 1
        self._check_micro_ingest()

        self.prev_user_text = exchange["user_text"]

        # Track for snapshot
        self.recent_exchanges.append(exchange)
        if len(self.recent_exchanges) > 10:
            self.recent_exchanges = self.recent_exchanges[-10:]
        self._check_snapshot()

    def watch(self):
        """Main loop — find active session, tail it, react."""
        log.info("Overwatch starting...")
        log.info(f"Conversations in DB: {self.conv.count()}")
        overdue = self.session_state.get("overdue_items", [])
        if overdue:
            log.info(f"Session state loaded: {len(overdue)} overdue items")

        while self.running:
            try:
                active = self.find_active_session()

                if active is None:
                    time.sleep(POLL_INTERVAL * 5)
                    continue

                # Heartbeat
                try:
                    mtime = active.stat().st_mtime
                    if time.time() - mtime > HEARTBEAT_TIMEOUT:
                        if self.recent_exchanges:
                            self._build_snapshot()
                        if self.pending_exchanges:
                            self._micro_ingest()
                        log.info(f"Session JSONL stale for {HEARTBEAT_TIMEOUT}s, exiting (orphan prevention)")
                        break
                except OSError:
                    pass

                # New session detected
                if active != self.current_jsonl:
                    if self.pending_exchanges:
                        self._micro_ingest()

                    self.current_jsonl = active
                    self.current_session_id = active.stem
                    self.last_position = active.stat().st_size
                    self.cooldowns.clear()
                    self.exchange_counter = 0
                    self.pending_exchanges = []
                    self.pending_exchanges_for_synthesis = []
                    self.exchanges_since_ingest = 0
                    self._pending_user = None
                    self._assistant_texts = []
                    self.last_ingest_time = time.time()
                    self.last_snapshot_time = 0
                    self.recent_exchanges = []
                    self.session_state = self._load_session_state()
                    log.info(f"Watching: {active.name} (session {self.current_session_id[:8]}...)")

                # Read new lines
                new_entries = self._read_new_lines(active)
                if not new_entries:
                    self._check_micro_ingest()
                    time.sleep(POLL_INTERVAL)
                    continue

                # Parse into exchanges
                exchanges = self._parse_exchanges(new_entries)
                if exchanges:
                    log.info(f"Parsed {len(exchanges)} exchange(s) from {len(new_entries)} entries")

                for exchange in exchanges:
                    self._process_exchange(exchange)
                    log.info(f"Processed: {exchange['user_text'][:60]}...")

                time.sleep(POLL_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Watch loop error: {e}")
                time.sleep(POLL_INTERVAL * 2)

        # Final flush
        if self.pending_exchanges:
            self._micro_ingest()
        log.info("Overwatch stopped.")

    def stop(self):
        self.running = False


def _handle_signal(signum, frame):
    log.info(f"Received signal {signum}, shutting down...")
    if _overwatch:
        _overwatch.stop()

_overwatch: Optional[Overwatch] = None


def main():
    global _overwatch
    PID_PATH.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        _overwatch = Overwatch()
        _overwatch.watch()
    finally:
        if PID_PATH.exists():
            PID_PATH.unlink()
        if INJECT_PATH.exists():
            INJECT_PATH.unlink()


if __name__ == "__main__":
    main()
