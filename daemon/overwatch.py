"""
Elara Overwatch — Live Memory Daemon

Tails the active Claude Code session JSONL in real-time,
searches ALL conversation history in ChromaDB for cross-references,
and injects relevant context via a hook file.

This is the real solution. Not a patch.
"""

import json
import os
import sys
import time
import math
import logging
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.conversations import get_conversations, ConversationMemory
from daemon.injector import format_injection, format_event_injection

# Paths
PROJECTS_DIR = Path.home() / ".claude" / "projects"
INJECT_PATH = Path("/tmp/elara-overwatch-inject.md")
PID_PATH = Path("/tmp/elara-overwatch.pid")
LOG_PATH = Path.home() / ".claude" / "elara-overwatch.log"

# Tuning
POLL_INTERVAL = 2.0          # seconds between file checks
RELEVANCE_THRESHOLD = 0.65   # minimum combined score to inject (0-1, higher = stricter)
COOLDOWN_SECONDS = 600       # 10 min cooldown per topic cluster
MAX_INJECTIONS_PER_CHECK = 3 # max results per injection
EVENT_THRESHOLD = 0.55       # lower threshold for event-triggered searches

# Event detection keywords
TASK_COMPLETE_WORDS = {"done", "built", "fixed", "shipped", "committed", "deployed", "pushed", "created", "finished"}
WINDING_DOWN_WORDS = {"anything else", "that's it", "what else", "done for", "calling it", "bye", "goodnight", "heading out"}

# System reminder pattern
import re
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)

log = logging.getLogger("overwatch")
log.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s [Overwatch] %(message)s')
_fh = logging.FileHandler(LOG_PATH)
_fh.setFormatter(_fmt)
log.addHandler(_fh)
# Only add stream handler if running interactively (not via nohup)
if os.isatty(1):
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    log.addHandler(_sh)


class Overwatch:
    def __init__(self):
        self.conv: ConversationMemory = get_conversations()
        self.last_position: int = 0
        self.current_session_id: str = ""
        self.current_jsonl: Optional[Path] = None
        self.cooldowns: Dict[str, float] = {}  # topic_hash -> last_inject_time
        self.prev_user_text: str = ""
        self.running: bool = True
        self.injection_count: int = 0

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

    def _clean_text(self, text: str) -> str:
        """Strip system-reminder blocks."""
        text = SYSTEM_REMINDER_RE.sub('', text)
        return text.strip()

    def _extract_text(self, entry: dict) -> Optional[str]:
        """Extract readable text from a JSONL entry."""
        msg = entry.get("message", {})
        content = msg.get("content", "")

        if isinstance(content, str):
            text = self._clean_text(content)
            return text if text and len(text) > 5 else None

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned and len(cleaned) > 5:
                        texts.append(cleaned)
            return "\n".join(texts) if texts else None

        return None

    def _read_new_lines(self, jsonl_path: Path) -> List[dict]:
        """Read new lines from the JSONL since last position."""
        entries = []
        try:
            file_size = jsonl_path.stat().st_size
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
        """Parse JSONL entries into user+assistant exchange pairs."""
        exchanges = []
        pending_user = None

        for entry in entries:
            entry_type = entry.get("type")

            if entry_type == "user":
                text = self._extract_text(entry)
                if text:
                    # Skip very short messages and system stuff
                    if text.startswith("<") or text.startswith("{"):
                        continue
                    pending_user = {
                        "user_text": text,
                        "timestamp": entry.get("timestamp", ""),
                    }

            elif entry_type == "assistant" and pending_user:
                text = self._extract_text(entry)
                if text:
                    exchanges.append({
                        "user_text": pending_user["user_text"],
                        "assistant_text": text,
                        "timestamp": pending_user["timestamp"],
                    })
                    pending_user = None

        return exchanges

    def _is_on_cooldown(self, topic_hash: str) -> bool:
        """Check if a topic is on cooldown."""
        if topic_hash not in self.cooldowns:
            return False
        elapsed = time.time() - self.cooldowns[topic_hash]
        return elapsed < COOLDOWN_SECONDS

    def _set_cooldown(self, topic_hash: str):
        """Set cooldown for a topic."""
        self.cooldowns[topic_hash] = time.time()

    def _topic_hash(self, text: str) -> str:
        """Simple hash for cooldown tracking — first 50 chars normalized."""
        import hashlib
        normalized = text.lower().strip()[:50]
        return hashlib.md5(normalized.encode()).hexdigest()[:8]

    def _detect_events(self, exchange: Dict[str, str]) -> List[Dict[str, Any]]:
        """Detect events that should trigger broader searches."""
        events = []
        assistant_lower = exchange["assistant_text"].lower()
        user_lower = exchange["user_text"].lower()

        # Task completion
        for word in TASK_COMPLETE_WORDS:
            if word in assistant_lower:
                events.append({
                    "type": "task_complete",
                    "text": exchange["assistant_text"],
                    "query": exchange["assistant_text"][:200],
                })
                break

        # Session winding down
        for phrase in WINDING_DOWN_WORDS:
            if phrase in user_lower or phrase in assistant_lower:
                events.append({
                    "type": "winding_down",
                    "text": exchange["user_text"],
                    "query": None,  # uses special queries
                })
                break

        return events

    def _search_history(self, text: str, threshold: float, n_results: int = 10) -> List[Dict[str, Any]]:
        """Search all conversation history, excluding current session."""
        try:
            results = self.conv.recall(text, n_results=n_results)
        except Exception as e:
            log.error(f"Search error: {e}")
            return []

        # Filter: above threshold, not current session, not on cooldown
        relevant = []
        for r in results:
            if r["score"] < threshold:
                continue
            if r["session_id"] == self.current_session_id:
                continue
            topic = self._topic_hash(r["content"])
            if self._is_on_cooldown(topic):
                continue
            relevant.append(r)

        return relevant[:MAX_INJECTIONS_PER_CHECK]

    def _search_for_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run broader searches triggered by events."""
        all_results = []

        for event in events:
            if event["type"] == "task_complete":
                results = self._search_history(
                    event["query"],
                    threshold=EVENT_THRESHOLD,
                    n_results=5,
                )
                for r in results:
                    r["_event"] = "task_complete"
                all_results.extend(results)

            elif event["type"] == "winding_down":
                # Search for unfulfilled intentions
                intention_queries = [
                    "plans for next session tomorrow",
                    "promises I made to him",
                    "things we should do want to try",
                    "drift companion therapist mode",
                    "remind me about",
                ]
                for q in intention_queries:
                    results = self._search_history(
                        q,
                        threshold=EVENT_THRESHOLD,
                        n_results=3,
                    )
                    for r in results:
                        r["_event"] = "winding_down"
                    all_results.extend(results)

        # Deduplicate by session_id + exchange_index
        seen = set()
        unique = []
        for r in all_results:
            key = f"{r['session_id']}:{r['exchange_index']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique[:MAX_INJECTIONS_PER_CHECK]

    def _write_inject(self, results: List[Dict[str, Any]], event_results: List[Dict[str, Any]] = None):
        """Write the inject file for the hook to pick up."""
        content = ""

        if results:
            content += format_injection(results)

        if event_results:
            if content:
                content += "\n"
            content += format_event_injection(event_results)

        if content:
            try:
                INJECT_PATH.write_text(content)
                self.injection_count += 1
                log.info(f"Injection #{self.injection_count}: {len(results or [])} cross-refs, {len(event_results or [])} event matches")

                # Set cooldowns for injected topics
                for r in (results or []) + (event_results or []):
                    self._set_cooldown(self._topic_hash(r["content"]))
            except OSError as e:
                log.error(f"Write error: {e}")

    def _process_exchange(self, exchange: Dict[str, str]):
        """Core logic: process one new exchange."""
        combined = exchange["user_text"] + " " + exchange["assistant_text"]

        # 1. Search all history for cross-references
        results = self._search_history(combined, threshold=RELEVANCE_THRESHOLD)

        # 2. Detect events
        events = self._detect_events(exchange)
        event_results = self._search_for_events(events) if events else []

        # 3. If anything worth injecting, write it
        if results or event_results:
            self._write_inject(results, event_results)

        self.prev_user_text = exchange["user_text"]

    def watch(self):
        """Main loop — find active session, tail it, react."""
        log.info("Overwatch starting...")
        log.info(f"Conversations in DB: {self.conv.count()}")

        while self.running:
            try:
                active = self.find_active_session()

                if active is None:
                    time.sleep(POLL_INTERVAL * 5)
                    continue

                # New session detected
                if active != self.current_jsonl:
                    self.current_jsonl = active
                    self.current_session_id = active.stem
                    self.last_position = active.stat().st_size  # start from end, don't process history
                    self.cooldowns.clear()
                    log.info(f"Watching: {active.name} (session {self.current_session_id[:8]}...)")

                # Read new lines
                new_entries = self._read_new_lines(active)
                if not new_entries:
                    time.sleep(POLL_INTERVAL)
                    continue

                # Parse into exchanges
                exchanges = self._parse_exchanges(new_entries)

                # Process each exchange
                for exchange in exchanges:
                    self._process_exchange(exchange)
                    log.debug(f"Processed: {exchange['user_text'][:60]}...")

                time.sleep(POLL_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Watch loop error: {e}")
                time.sleep(POLL_INTERVAL * 2)

        log.info("Overwatch stopped.")

    def stop(self):
        """Signal the watch loop to stop."""
        self.running = False


def _handle_signal(signum, frame):
    """Graceful shutdown on SIGTERM/SIGINT."""
    log.info(f"Received signal {signum}, shutting down...")
    if _overwatch:
        _overwatch.stop()

_overwatch: Optional[Overwatch] = None


def main():
    global _overwatch

    # Write PID file
    PID_PATH.write_text(str(os.getpid()))

    # Signal handlers
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        _overwatch = Overwatch()
        _overwatch.watch()
    finally:
        # Cleanup
        if PID_PATH.exists():
            PID_PATH.unlink()
        if INJECT_PATH.exists():
            INJECT_PATH.unlink()


if __name__ == "__main__":
    main()
