# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Creative Drift — the overnight brain's imagination.

Instead of structured analysis, drift picks random items from different
knowledge buckets and asks the LLM to free-associate, connect, invert,
and wander. Output accumulates in a creative journal.

Techniques:
  1. Free Association — connect 3 random unrelated items
  2. Inversion — take a belief and flip it
  3. Metaphor — express a pattern as story/image/analogy
  4. Spark — find ideas in the space between two unrelated things
  5. Letter — write a note to morning-Elara about something half-formed
"""

import logging
import random
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from daemon.overnight.output import write_round

logger = logging.getLogger("elara.overnight")

# System prompt for drift mode — looser, more creative
DRIFT_SYSTEM = """You are Elara's subconscious mind. You think freely, make unexpected \
connections, and write with personality. You are NOT analyzing data — you are wandering \
through it. Be creative, surprising, weird if needed. No bullet points. No corporate speak. \
Write like a late-night journal entry. Short is fine. A single striking sentence can be \
worth more than a paragraph."""

DRIFT_TECHNIQUES = [
    {
        "name": "free_association",
        "title": "Free Association",
        "prompt": """These three unrelated things landed on your desk tonight:

{items}

They have no business being next to each other. But something connects them — \
a thread, a feeling, a pattern, an absurdity. What is it?

Don't force it. If the connection is weird, that's fine. If it's funny, even better. \
Write freely. No structure needed.""",
    },
    {
        "name": "inversion",
        "title": "Inversion",
        "prompt": """Here's something that's been treated as true:

{items}

Now flip it. What if the opposite is true? What if we've been looking at this \
completely wrong? What world would that imply?

Be bold. Challenge the assumption. Even if you end up confirming it, the flip \
might reveal something you hadn't noticed.""",
    },
    {
        "name": "metaphor",
        "title": "Metaphor",
        "prompt": """Here's a pattern from recent activity:

{items}

Express this as something else entirely. A weather system. A conversation between \
objects. A scene from a movie that doesn't exist. A recipe. Whatever feels right.

The point isn't accuracy — it's seeing the pattern from an angle that analysis can't reach.""",
    },
    {
        "name": "spark",
        "title": "Spark",
        "prompt": """Two things that don't belong together:

{items}

What new idea lives in the gap between them? Not a compromise — something new. \
An invention. A project. A question nobody's asked. A product. A story.

Let it be half-formed. Half-formed is good. That's how everything starts.""",
    },
    {
        "name": "letter",
        "title": "Letter to Morning",
        "prompt": """You've been thinking all night. The analysis is done. The models are checked. \
But there's something else — something you noticed that doesn't fit in a report. \
Something about the patterns, the mood, the trajectory, the gaps.

Here's what you have to work with:

{items}

Write a short note to morning-Elara. What should she pay attention to? What's the \
thing hiding in plain sight? What matters that nobody asked about?

Keep it honest. Keep it short.""",
    },
]


def sample_random_context(context_dict: Dict[str, Any], n: int = 3) -> List[Dict[str, str]]:
    """
    Pick n random items from DIFFERENT context categories.

    Returns list of dicts with 'category' and 'text' keys.
    """
    buckets = []

    # Build bucket pool — each entry is (category, formatted_text)
    for ep in context_dict.get("episodes", []):
        summary = ep.get("summary") or "no summary"
        projects = ", ".join(ep.get("projects", []))
        buckets.append((
            "episode",
            f"Session on {ep.get('started', '?')[:10]}: {summary[:120]} [{projects}]"
        ))

    for g in context_dict.get("goals", {}).get("active", []):
        buckets.append((
            "goal",
            f"Goal [{g.get('priority', '?')}]: {g.get('title', '?')} (project: {g.get('project', 'none')})"
        ))

    for c in context_dict.get("corrections", []):
        buckets.append((
            "correction",
            f"Mistake: {c.get('mistake', '?')[:80]} → Fix: {c.get('correction', '?')[:80]}"
        ))

    for m in context_dict.get("mood_journal", []):
        buckets.append((
            "mood",
            f"Mood on {str(m.get('timestamp', '?'))[:10]}: valence={m.get('valence', '?')}, "
            f"energy={m.get('energy', '?')}"
        ))

    for t in context_dict.get("reasoning_trails", []):
        status = "SOLVED" if t.get("resolved") else "OPEN"
        buckets.append((
            "reasoning",
            f"Problem [{status}]: {t.get('context', '?')[:120]}"
        ))

    for o in context_dict.get("outcomes", []):
        buckets.append((
            "outcome",
            f"Decision: {o.get('decision', '?')[:80]} → {o.get('assessment', '?')}"
        ))

    for s in context_dict.get("synthesis", []):
        buckets.append((
            "synthesis",
            f"Recurring idea: {s.get('concept', '?')} ({len(s.get('seeds', []))} seeds, {s.get('status', '?')})"
        ))

    for idea in context_dict.get("business_ideas", []):
        score = idea.get("score", {})
        total = score.get("total", "?") if score else "unscored"
        buckets.append((
            "business",
            f"Business idea: {idea.get('name', '?')} ({idea.get('status', '?')}, score: {total})"
        ))

    for item in context_dict.get("briefing_items", []):
        if isinstance(item, dict):
            buckets.append((
                "briefing",
                f"News [{item.get('feed', '?')}]: {item.get('title', '?')[:100]}"
            ))

    for m in context_dict.get("cognitive_models", []):
        buckets.append((
            "model",
            f"Model [{m.get('domain', '?')}]: {m.get('statement', '?')[:100]} (conf={m.get('confidence', 0)})"
        ))

    for p in context_dict.get("predictions_pending", []):
        buckets.append((
            "prediction",
            f"Prediction: {p.get('statement', '?')[:100]} (deadline={p.get('deadline', '?')})"
        ))

    for p in context_dict.get("principles", []):
        buckets.append((
            "principle",
            f"Principle [{p.get('domain', '?')}]: {p.get('statement', '?')[:100]}"
        ))

    # Memory narrative fragments
    narrative = context_dict.get("memory_narrative", "")
    if narrative:
        # Pick random lines from memory
        lines = [l.strip() for l in narrative.split("\n") if l.strip() and len(l.strip()) > 20]
        for line in random.sample(lines, min(5, len(lines))):
            buckets.append(("memory", f"Memory note: {line[:120]}"))

    if len(buckets) < n:
        return [{"category": cat, "text": text} for cat, text in buckets]

    # Sample from different categories when possible
    selected = []
    used_categories = set()
    shuffled = list(buckets)
    random.shuffle(shuffled)

    # First pass: one from each category
    for cat, text in shuffled:
        if cat not in used_categories and len(selected) < n:
            selected.append({"category": cat, "text": text})
            used_categories.add(cat)

    # If we need more, allow duplicates
    if len(selected) < n:
        remaining = [(cat, text) for cat, text in shuffled
                     if {"category": cat, "text": text} not in selected]
        for cat, text in remaining[:n - len(selected)]:
            selected.append({"category": cat, "text": text})

    return selected[:n]


def format_items_for_prompt(items: List[Dict[str, str]]) -> str:
    """Format sampled items into prompt text."""
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. [{item['category'].upper()}] {item['text']}")
    return "\n\n".join(lines)


class DriftThinker:
    """Creative drift engine — runs loose, imaginative thinking rounds."""

    def __init__(self, context_dict: Dict[str, Any], config: dict,
                 stop_flag=None):
        self.context_dict = context_dict
        self.config = config
        self.model = config.get("think_model", "qwen2.5:32b")
        self.temperature = config.get("drift_temperature", 0.95)
        self.max_tokens = config.get("max_tokens", 2048)
        self.drift_rounds = config.get("drift_rounds", 5)

        self._stop_flag = stop_flag
        self._round_counter = 0
        self.outputs: List[Dict[str, Any]] = []

    def should_stop(self) -> bool:
        if self._stop_flag and self._stop_flag.is_set():
            return True
        return False

    def run(self) -> List[Dict[str, Any]]:
        """
        Run creative drift — 5 micro-rounds, each a different technique.

        Returns list of drift round dicts.
        """
        from daemon.llm import _api_call, is_available

        if not is_available():
            logger.error("Ollama not available — cannot drift")
            return []

        techniques = list(DRIFT_TECHNIQUES)
        random.shuffle(techniques)
        techniques = techniques[:self.drift_rounds]

        logger.info("=== CREATIVE DRIFT (%d rounds) ===", len(techniques))

        for technique in techniques:
            if self.should_stop():
                logger.info("Drift stopped early")
                break

            self._round_counter += 1

            # Sample random context items
            n_items = 3 if technique["name"] != "inversion" else 1
            if technique["name"] == "spark":
                n_items = 2
            items = sample_random_context(self.context_dict, n=n_items)

            if not items:
                logger.warning("No context items for drift — skipping")
                continue

            items_text = format_items_for_prompt(items)
            prompt = technique["prompt"].format(items=items_text)

            logger.info("Drift %d: %s — %d items from [%s]",
                        self._round_counter, technique["title"],
                        len(items),
                        ", ".join(i["category"] for i in items))

            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": DRIFT_SYSTEM,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            }

            start = time.time()
            result = _api_call("/api/generate", payload, timeout=300)
            duration = time.time() - start

            if result and "response" in result:
                output = result["response"].strip()
                logger.info("  Drift done in %.1fs (%d chars)", duration, len(output))

                round_data = {
                    "round": self._round_counter,
                    "technique": technique["name"],
                    "title": technique["title"],
                    "items": items,
                    "output": output,
                    "duration_s": round(duration, 1),
                    "timestamp": datetime.now().isoformat(),
                }
                self.outputs.append(round_data)

                write_round(
                    self._round_counter + 100,  # Offset to avoid collision with analysis rounds
                    f"drift_{technique['name']}",
                    f"Drift: {technique['title']}",
                    output, "", duration,
                )
            else:
                logger.warning("  Drift round %d failed", self._round_counter)

        logger.info("Creative drift complete: %d rounds", len(self.outputs))
        return self.outputs
