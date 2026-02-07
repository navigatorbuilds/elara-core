"""
Overwatch micro-ingestion — triage and ChromaDB ingestion.
"""

import time
from typing import List, Dict

from daemon import llm
from daemon.overwatch.config import (
    MICRO_INGEST_EXCHANGES, MICRO_INGEST_SECONDS, log,
)

# Optional: synthesis for recurring idea detection
try:
    from daemon.synthesis import check_for_recurring_ideas
    SYNTHESIS_AVAILABLE = True
except ImportError:
    SYNTHESIS_AVAILABLE = False


class IngestMixin:
    """Mixin for micro-ingestion and triage."""

    def _micro_ingest(self):
        """Ingest pending exchanges into ChromaDB for same-session searchability.
        Uses LLM for triage when available — classifies and scores importance."""
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
                    # Use importance score (1.5B model's worth_keeping is unreliable)
                    importance = triage.get("importance", 0.5)
                    if isinstance(importance, (int, float)) and importance < 0.25:
                        log.debug(f"Triage skip (importance {importance}): {ex['user_text'][:50]}...")
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

        # Synthesis auto-detection
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
