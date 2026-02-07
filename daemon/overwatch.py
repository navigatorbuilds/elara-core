"""
Elara Overwatch — Live Memory Daemon

Tails the active Claude Code session JSONL in real-time,
searches ALL conversation history in ChromaDB for cross-references,
and injects relevant context via a hook file.

v2: Priority integration, micro-ingestion, feedback loop prevention,
    heartbeat, atomic writes.

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
from daemon import llm

# Optional: synthesis for recurring idea detection
try:
    from daemon.synthesis import check_for_recurring_ideas
    SYNTHESIS_AVAILABLE = True
except ImportError:
    SYNTHESIS_AVAILABLE = False

# Paths
PROJECTS_DIR = Path.home() / ".claude" / "projects"
INJECT_PATH = Path.home() / ".claude" / "elara-overwatch-inject.md"
INJECT_TMP_PATH = INJECT_PATH.with_suffix(".tmp")
PID_PATH = Path.home() / ".claude" / "elara-overwatch.pid"
LOG_PATH = Path.home() / ".claude" / "elara-overwatch.log"
SESSION_STATE_PATH = Path.home() / ".claude" / "elara-session-state.json"

# Tuning
POLL_INTERVAL = 2.0          # seconds between file checks
RELEVANCE_THRESHOLD = 0.65   # minimum combined score to inject (0-1, higher = stricter)
COOLDOWN_SECONDS = 600       # 10 min cooldown per topic cluster
MAX_INJECTIONS_PER_CHECK = 3 # max results per injection
EVENT_THRESHOLD = 0.55       # lower threshold for event-triggered searches
HEARTBEAT_TIMEOUT = 300      # 5 min — exit if JSONL stale (session likely dead)
TWENTY_FOUR_HOURS = 86400    # seconds — downweight recent results to prevent feedback loops
RECENT_DOWNWEIGHT = 0.5      # multiply score by this for results < 24h old
OVERDUE_BOOST = 0.15         # score boost for results matching overdue items

# Micro-ingestion
MICRO_INGEST_EXCHANGES = 5   # ingest every N exchanges
MICRO_INGEST_SECONDS = 600   # or every N seconds, whichever first

# Session snapshot — lightweight state for boot continuity
SNAPSHOT_PATH = Path.home() / ".claude" / "elara-session-snapshot.json"
SNAPSHOT_INTERVAL = 1200     # 20 min between snapshots
SNAPSHOT_MIN_EXCHANGES = 3   # need at least 3 exchanges before first snapshot

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

        # Priority integration — loaded from session state written by boot priority engine
        self.session_state: Dict[str, Any] = self._load_session_state()

        # Micro-ingestion tracking
        self.exchanges_since_ingest: int = 0
        self.last_ingest_time: float = time.time()
        self.pending_exchanges: List[Dict[str, str]] = []
        self.pending_exchanges_for_synthesis: List[Dict[str, str]] = []
        self.exchange_counter: int = 0  # monotonic counter for exchange_index

        # Cross-poll parsing state — user and assistant entries often land in different batches
        self._pending_user: Optional[Dict[str, str]] = None
        self._assistant_texts: List[str] = []

        # Session snapshot tracking
        self.last_snapshot_time: float = 0
        self.recent_exchanges: List[Dict[str, str]] = []  # rolling window for snapshot context

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
        """Load session state written by boot priority engine."""
        if SESSION_STATE_PATH.exists():
            try:
                return json.loads(SESSION_STATE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _micro_ingest(self):
        """Ingest pending exchanges into ChromaDB for same-session searchability.
        Uses Ollama for triage when available — classifies and scores importance."""
        if not self.pending_exchanges:
            return
        try:
            ingested = 0
            triaged = 0
            for ex in self.pending_exchanges:
                # Try LLM triage — classify and score importance
                triage = llm.triage_memory(ex["user_text"], ex["assistant_text"])
                if triage:
                    triaged += 1
                    # Skip low-importance exchanges (greetings, confirmations)
                    if not triage.get("worth_keeping", True):
                        log.debug(f"Triage skip: {ex['user_text'][:50]}...")
                        continue

                ok = self.conv.ingest_exchange(
                    user_text=ex["user_text"],
                    assistant_text=ex["assistant_text"],
                    timestamp=ex.get("timestamp", ""),
                    session_id=self.current_session_id,
                    exchange_index=ex.get("exchange_index", -1),
                )
                if ok:
                    ingested += 1
            triage_msg = f", {triaged} triaged by LLM" if triaged else ""
            log.info(f"Micro-ingested {ingested}/{len(self.pending_exchanges)} exchanges{triage_msg}")
        except Exception as e:
            log.error(f"Micro-ingest error: {e}")
        # Synthesis auto-detection — check ingested exchanges for recurring ideas
        if SYNTHESIS_AVAILABLE and ingested > 0:
            try:
                synthesis_exchanges = [
                    {
                        "text": ex["user_text"] + " " + ex["assistant_text"],
                        "session_id": self.current_session_id,
                        "timestamp": ex.get("timestamp", ""),
                    }
                    for ex in self.pending_exchanges_for_synthesis
                ]
                if synthesis_exchanges:
                    reinforced = check_for_recurring_ideas(synthesis_exchanges)
                    if reinforced:
                        log.info(f"Synthesis: {len(reinforced)} idea(s) reinforced from conversation")
            except Exception as e:
                log.debug(f"Synthesis check error: {e}")

        self.pending_exchanges = []
        self.pending_exchanges_for_synthesis = []
        self.exchanges_since_ingest = 0
        self.last_ingest_time = time.time()

    def _check_micro_ingest(self):
        """Check if it's time to micro-ingest."""
        if (self.exchanges_since_ingest >= MICRO_INGEST_EXCHANGES or
                (self.pending_exchanges and time.time() - self.last_ingest_time > MICRO_INGEST_SECONDS)):
            self._micro_ingest()

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
        Accumulates text across multiple assistant entries (tool_use and thinking
        blocks produce entries with no text — we skip those).
        """
        exchanges = []

        for entry in entries:
            entry_type = entry.get("type")

            if entry_type == "user":
                text = self._extract_text(entry)
                if text:
                    log.debug(f"User text extracted ({len(text)} chars): {text[:60]}")
                if not text or text.startswith("<") or text.startswith("{"):
                    # Empty user entry (tool permission, hook, tool_result) — ignore, don't reset state
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

        # Don't flush at end — wait for next user entry to confirm exchange is complete.
        # This prevents premature pairing when assistant is still generating.

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
        """Search all conversation history, excluding current session.
        Applies 24h downweight (feedback loop prevention) and overdue boost."""
        try:
            results = self.conv.recall(text, n_results=n_results)
        except Exception as e:
            log.error(f"Search error: {e}")
            return []

        now = time.time()
        overdue_items = self.session_state.get("overdue_items", [])

        # Filter: above threshold, not current session, not on cooldown
        relevant = []
        for r in results:
            score = r["score"]

            # 24h downweight — prevent feedback loops from recent injections
            epoch = r.get("epoch", 0)
            if epoch > 0 and (now - epoch) < TWENTY_FOUR_HOURS:
                score *= RECENT_DOWNWEIGHT

            # Overdue boost — if result content matches an overdue item, boost it
            if overdue_items:
                content_lower = r.get("content", "").lower()
                for overdue_text in overdue_items:
                    # Check if 2+ significant words from overdue item appear in result
                    words = [w for w in overdue_text.lower().split() if len(w) > 3][:5]
                    matches = sum(1 for w in words if w in content_lower)
                    if matches >= 2:
                        score = min(1.0, score + OVERDUE_BOOST)
                        break

            if score < threshold:
                continue
            if r["session_id"] == self.current_session_id:
                continue
            topic = self._topic_hash(r["content"])
            if self._is_on_cooldown(topic):
                continue

            r["score"] = score  # update with adjusted score
            relevant.append(r)

        # Ollama relevance judgment — filter false positives from cosine similarity
        if relevant and llm.is_available():
            judged = []
            for r in relevant[:MAX_INJECTIONS_PER_CHECK + 2]:  # judge a few extra
                judgment = llm.judge_relevance(
                    current_text=text,
                    historical_text=r.get("content", r.get("user_text", "")),
                )
                if judgment and judgment.get("relevant"):
                    # Blend Ollama importance with cosine score
                    ollama_importance = judgment.get("importance", 0.5)
                    r["score"] = r["score"] * 0.6 + ollama_importance * 0.4
                    r["_llm_reason"] = judgment.get("reason", "")
                    judged.append(r)
                elif judgment is None:
                    # Ollama failed mid-batch, keep remaining on score alone
                    judged.append(r)
                else:
                    log.debug(f"LLM filtered: {r.get('content', '')[:50]}... — {judgment.get('reason', '')}")
            relevant = judged

        return relevant[:MAX_INJECTIONS_PER_CHECK]

    def _search_for_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run broader searches triggered by events. Uses Ollama for smarter queries."""
        all_results = []

        for event in events:
            if event["type"] == "task_complete":
                # Try Ollama for smarter search queries
                llm_queries = llm.generate_search_queries(event["query"], n_queries=3)
                if llm_queries:
                    log.info(f"LLM generated {len(llm_queries)} queries for task_complete")
                    for q in llm_queries:
                        results = self._search_history(q, threshold=EVENT_THRESHOLD, n_results=3)
                        for r in results:
                            r["_event"] = "task_complete"
                        all_results.extend(results)
                else:
                    # Fallback: use raw text
                    results = self._search_history(
                        event["query"],
                        threshold=EVENT_THRESHOLD,
                        n_results=5,
                    )
                    for r in results:
                        r["_event"] = "task_complete"
                    all_results.extend(results)

            elif event["type"] == "winding_down":
                # Pull queries from session state (overdue items, reminders)
                overdue = self.session_state.get("overdue_items", [])
                reminders = self.session_state.get("reminders", [])
                intention_queries = overdue + reminders
                if not intention_queries:
                    intention_queries = [
                        "plans for next session tomorrow",
                        "promises I made to him",
                        "things we should do want to try",
                    ]
                for q in intention_queries[:5]:
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
                # Atomic write: .tmp → rename (prevents partial reads by hook)
                INJECT_TMP_PATH.write_text(content)
                os.rename(str(INJECT_TMP_PATH), str(INJECT_PATH))
                self.injection_count += 1
                log.info(f"Injection #{self.injection_count}: {len(results or [])} cross-refs, {len(event_results or [])} event matches")

                # Set cooldowns for injected topics
                for r in (results or []) + (event_results or []):
                    self._set_cooldown(self._topic_hash(r["content"]))

                # Track injected topics in session state
                self._track_injected_topics(results, event_results)
            except OSError as e:
                log.error(f"Write error: {e}")

    def _track_injected_topics(self, results: List[Dict], event_results: List[Dict]):
        """Track injected topics in session state to prevent cross-session duplicates."""
        try:
            if SESSION_STATE_PATH.exists():
                state = json.loads(SESSION_STATE_PATH.read_text())
            else:
                state = self.session_state

            topics = state.get("injected_topics", [])
            for r in (results or []) + (event_results or []):
                preview = r.get("user_text_preview", r.get("content", "")[:80])
                if preview and preview not in topics:
                    topics.append(preview)
            state["injected_topics"] = topics[-50:]  # cap at 50

            tmp = SESSION_STATE_PATH.with_suffix('.tmp')
            tmp.write_text(json.dumps(state, indent=2))
            os.rename(str(tmp), str(SESSION_STATE_PATH))
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"Session state update error: {e}")

    def _build_snapshot(self) -> None:
        """Build a session snapshot — one file, always overwritten.

        Three fields for boot:
        - continuation: for quick reboots (<30 min) — what we were just doing (Ollama)
        - greeting_hint: for fresh sessions (hours later) — casual summary (Ollama)
        - last_exchanges: raw transcript of last 5 exchanges — the actual words, no interpretation
        """
        if not self.recent_exchanges:
            return

        # Get last 5 exchanges for context
        recent = self.recent_exchanges[-5:]
        context_parts = []
        for ex in recent:
            user_short = ex["user_text"][:150]
            assistant_short = ex["assistant_text"][:150]
            context_parts.append(f"User: {user_short}\nAssistant: {assistant_short}")
        context = "\n---\n".join(context_parts)

        # Raw exchanges — the actual words, no LLM interpretation
        raw_exchanges = []
        for ex in recent:
            raw_exchanges.append({
                "user": ex["user_text"][:300],
                "assistant": ex["assistant_text"][:300],
            })

        # Ask LLM for continuation (what we were mid-thought on)
        continuation = llm.query(
            "What were they working on? 1-2 sentences, no greeting.\n\n"
            f"{context}",
            temperature=0.3,
            max_tokens=50,
        )

        # Ask LLM for greeting hint (session summary for fresh boots)
        greeting_hint = llm.query(
            "One casual sentence: what got done this session?\n\n"
            f"{context}",
            temperature=0.4,
            max_tokens=30,
        )

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.current_session_id,
            "exchange_count": self.exchange_counter,
            "continuation": continuation or self._fallback_continuation(),
            "greeting_hint": greeting_hint or self._fallback_greeting(),
            "last_exchanges": raw_exchanges,
        }

        try:
            tmp = SNAPSHOT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, indent=2))
            os.rename(str(tmp), str(SNAPSHOT_PATH))
            log.info(f"Snapshot written ({self.exchange_counter} exchanges)")
        except OSError as e:
            log.error(f"Snapshot write error: {e}")

    def _fallback_continuation(self) -> str:
        """Fallback continuation when Ollama is unavailable."""
        if self.recent_exchanges:
            last = self.recent_exchanges[-1]
            return f"Last: {last['user_text'][:100]}"
        return ""

    def _fallback_greeting(self) -> str:
        """Fallback greeting hint when Ollama is unavailable."""
        return f"Session had {self.exchange_counter} exchanges."

    def _check_snapshot(self) -> None:
        """Check if it's time to write a snapshot."""
        now = time.time()
        if (self.exchange_counter >= SNAPSHOT_MIN_EXCHANGES
                and now - self.last_snapshot_time > SNAPSHOT_INTERVAL):
            self._build_snapshot()
            self.last_snapshot_time = now

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

        # 4. Queue for micro-ingestion + synthesis detection
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

                # Heartbeat: if JSONL hasn't been modified in 5 min, session is dead
                try:
                    mtime = active.stat().st_mtime
                    if time.time() - mtime > HEARTBEAT_TIMEOUT:
                        # Final snapshot + flush before exiting
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
                    # Flush pending micro-ingestion from previous session
                    if self.pending_exchanges:
                        self._micro_ingest()

                    self.current_jsonl = active
                    self.current_session_id = active.stem
                    self.last_position = active.stat().st_size  # start from end, don't process history
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

                    # Reload session state (may have been updated by new boot)
                    self.session_state = self._load_session_state()

                    log.info(f"Watching: {active.name} (session {self.current_session_id[:8]}...)")

                # Read new lines
                new_entries = self._read_new_lines(active)
                if not new_entries:
                    # Still check time-based micro-ingest even when idle
                    self._check_micro_ingest()
                    time.sleep(POLL_INTERVAL)
                    continue

                # Parse into exchanges
                exchanges = self._parse_exchanges(new_entries)

                if exchanges:
                    log.info(f"Parsed {len(exchanges)} exchange(s) from {len(new_entries)} entries")

                # Process each exchange
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
