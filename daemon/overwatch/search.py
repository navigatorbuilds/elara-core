"""
Overwatch search — history search, event detection, LLM filtering, injection writing.
"""

import os
import json
import time
import hashlib
from typing import List, Dict, Any, Optional

from daemon import llm
from daemon.injector import format_injection, format_event_injection
from daemon.overwatch.config import (
    RELEVANCE_THRESHOLD, COOLDOWN_SECONDS, MAX_INJECTIONS_PER_CHECK,
    EVENT_THRESHOLD, TWENTY_FOUR_HOURS, RECENT_DOWNWEIGHT, OVERDUE_BOOST,
    TASK_COMPLETE_WORDS, WINDING_DOWN_WORDS,
    INJECT_PATH, INJECT_TMP_PATH, SESSION_STATE_PATH, log,
)


class SearchMixin:
    """Mixin for history search, event detection, and injection."""

    def _is_on_cooldown(self, topic_hash: str) -> bool:
        if topic_hash not in self.cooldowns:
            return False
        return time.time() - self.cooldowns[topic_hash] < COOLDOWN_SECONDS

    def _set_cooldown(self, topic_hash: str):
        self.cooldowns[topic_hash] = time.time()

    def _topic_hash(self, text: str) -> str:
        normalized = text.lower().strip()[:50]
        return hashlib.md5(normalized.encode()).hexdigest()[:8]

    def _detect_events(self, exchange: Dict[str, str]) -> List[Dict[str, Any]]:
        """Detect events that should trigger broader searches."""
        events = []
        assistant_lower = exchange["assistant_text"].lower()
        user_lower = exchange["user_text"].lower()

        for word in TASK_COMPLETE_WORDS:
            if word in assistant_lower:
                events.append({
                    "type": "task_complete",
                    "text": exchange["assistant_text"],
                    "query": exchange["assistant_text"][:200],
                })
                break

        for phrase in WINDING_DOWN_WORDS:
            if phrase in user_lower or phrase in assistant_lower:
                events.append({
                    "type": "winding_down",
                    "text": exchange["user_text"],
                    "query": None,
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

        now = time.time()
        overdue_items = self.session_state.get("overdue_items", [])

        relevant = []
        for r in results:
            score = r["score"]

            # 24h downweight — prevent feedback loops
            epoch = r.get("epoch", 0)
            if epoch > 0 and (now - epoch) < TWENTY_FOUR_HOURS:
                score *= RECENT_DOWNWEIGHT

            # Overdue boost
            if overdue_items:
                content_lower = r.get("content", "").lower()
                for overdue_text in overdue_items:
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

            r["score"] = score
            relevant.append(r)

        # LLM relevance judgment — filter false positives
        if relevant and llm.is_available():
            judged = []
            for r in relevant[:MAX_INJECTIONS_PER_CHECK + 2]:
                judgment = llm.judge_relevance(
                    current_text=text,
                    historical_text=r.get("content", r.get("user_text", "")),
                )
                if judgment and judgment.get("relevant"):
                    ollama_importance = judgment.get("importance", 0.5)
                    r["score"] = r["score"] * 0.6 + ollama_importance * 0.4
                    r["_llm_reason"] = judgment.get("reason", "")
                    judged.append(r)
                elif judgment is None:
                    judged.append(r)
                else:
                    log.debug(f"LLM filtered: {r.get('content', '')[:50]}... — {judgment.get('reason', '')}")
            relevant = judged

        return relevant[:MAX_INJECTIONS_PER_CHECK]

    def _search_for_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run broader searches triggered by events."""
        all_results = []

        for event in events:
            if event["type"] == "task_complete":
                llm_queries = llm.generate_search_queries(event["query"], n_queries=3)
                if llm_queries:
                    log.info(f"LLM generated {len(llm_queries)} queries for task_complete")
                    for q in llm_queries:
                        results = self._search_history(q, threshold=EVENT_THRESHOLD, n_results=3)
                        for r in results:
                            r["_event"] = "task_complete"
                        all_results.extend(results)
                else:
                    results = self._search_history(event["query"], threshold=EVENT_THRESHOLD, n_results=5)
                    for r in results:
                        r["_event"] = "task_complete"
                    all_results.extend(results)

            elif event["type"] == "winding_down":
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
                    results = self._search_history(q, threshold=EVENT_THRESHOLD, n_results=3)
                    for r in results:
                        r["_event"] = "winding_down"
                    all_results.extend(results)

        # Deduplicate
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
                INJECT_TMP_PATH.write_text(content)
                os.rename(str(INJECT_TMP_PATH), str(INJECT_PATH))
                self.injection_count += 1
                log.info(f"Injection #{self.injection_count}: {len(results or [])} cross-refs, {len(event_results or [])} event matches")
                for r in (results or []) + (event_results or []):
                    self._set_cooldown(self._topic_hash(r["content"]))
                self._track_injected_topics(results, event_results)
            except OSError as e:
                log.error(f"Write error: {e}")

    def _track_injected_topics(self, results: List[Dict], event_results: List[Dict]):
        """Track injected topics in session state."""
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
            state["injected_topics"] = topics[-50:]
            tmp = SESSION_STATE_PATH.with_suffix('.tmp')
            tmp.write_text(json.dumps(state, indent=2))
            os.rename(str(tmp), str(SESSION_STATE_PATH))
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"Session state update error: {e}")
