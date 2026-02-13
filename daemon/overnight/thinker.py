# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight Thinker — core thinking loop.

Runs exploratory (8 phases) and directed (5 phases per problem) thinking
using a local LLM via Ollama. Each round builds on previous output.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from daemon.overnight.prompts import (
    SYSTEM_PROMPT, EXPLORATORY_PHASES, DIRECTED_PHASES,
)
from daemon.overnight.research import research_if_needed
from daemon.overnight.output import write_round

logger = logging.getLogger("elara.overnight")


class OvernightThinker:
    """Core thinking engine — runs LLM through themed phases."""

    def __init__(self, context_text: str, config: dict, stop_flag=None):
        self.context_text = context_text
        self.config = config
        self.model = config.get("think_model", "qwen2.5:32b")
        self.max_tokens = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.7)
        self.enable_research = config.get("enable_research", True)
        self.max_hours = config.get("max_hours", 6.0)
        self.stop_at = config.get("stop_at", "07:00")
        self.rounds_per_problem = config.get("rounds_per_problem", 5)

        self._start_time = datetime.now()
        self._stop_flag = stop_flag  # threading.Event for graceful stop
        self._round_counter = 0
        self._research_queries = 0

    def should_stop(self) -> bool:
        """Check if we should stop thinking (time limit or signal)."""
        # External stop signal
        if self._stop_flag and self._stop_flag.is_set():
            logger.info("Stop signal received")
            return True

        # Max hours
        elapsed = (datetime.now() - self._start_time).total_seconds() / 3600
        if elapsed >= self.max_hours:
            logger.info("Max hours (%.1f) reached", self.max_hours)
            return True

        # Stop-at time
        try:
            h, m = map(int, self.stop_at.split(":"))
            stop_time = datetime.now().replace(hour=h, minute=m, second=0)
            # If stop_at is before start (e.g. start at 23:00, stop at 07:00),
            # add a day
            if stop_time < self._start_time:
                stop_time += timedelta(days=1)
            if datetime.now() >= stop_time:
                logger.info("Stop-at time %s reached", self.stop_at)
                return True
        except (ValueError, AttributeError):
            pass

        return False

    def think_round(self, prompt: str, phase_name: str, phase_title: str) -> Optional[str]:
        """
        One LLM call. Returns the model's response or None on failure.
        """
        from daemon.llm import _api_call, is_available

        if not is_available():
            logger.error("Ollama not available — cannot think")
            return None

        self._round_counter += 1
        logger.info("Round %d: %s — %s", self._round_counter, phase_name, phase_title)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        start = time.time()
        result = _api_call("/api/generate", payload, timeout=600)
        duration = time.time() - start

        if result and "response" in result:
            output = result["response"].strip()
            logger.info("  Done in %.1fs (%d chars)", duration, len(output))
            return output
        else:
            logger.warning("  Round %d failed (no response)", self._round_counter)
            return None

    def run_exploratory(self) -> List[Dict[str, Any]]:
        """
        Run 8 exploratory phases. Each builds on previous output.
        Returns list of round dicts.
        """
        logger.info("=== EXPLORATORY THINKING (%d phases) ===", len(EXPLORATORY_PHASES))
        rounds = []
        prev_output = ""

        for phase in EXPLORATORY_PHASES:
            if self.should_stop():
                logger.info("Stopping exploratory thinking early (round %d/%d)",
                          len(rounds), len(EXPLORATORY_PHASES))
                break

            # Build prompt from template
            research_text = ""
            prompt = phase["prompt"].format(
                context=self.context_text,
                prev_output=prev_output[-3000:] if prev_output else "(first round)",
                research=research_text,
            )

            start = time.time()
            output = self.think_round(prompt, phase["name"], phase["title"])
            duration = time.time() - start

            if output is None:
                logger.warning("Phase '%s' produced no output, skipping", phase["name"])
                continue

            # Check for research requests
            research_text = research_if_needed(output, enable=self.enable_research)
            if research_text:
                self._research_queries += research_text.count("Search: ")
                # Re-run with research if we got results
                prompt_with_research = phase["prompt"].format(
                    context=self.context_text,
                    prev_output=prev_output[-3000:] if prev_output else "(first round)",
                    research=research_text,
                )
                enriched = self.think_round(
                    prompt_with_research,
                    f"{phase['name']}_enriched",
                    f"{phase['title']} (with research)",
                )
                if enriched:
                    output = enriched
                    duration = time.time() - start

            round_data = {
                "round": self._round_counter,
                "phase": phase["name"],
                "title": phase["title"],
                "output": output,
                "research": research_text,
                "duration_s": duration,
            }
            rounds.append(round_data)
            write_round(self._round_counter, phase["name"], phase["title"],
                       output, research_text, duration)

            # Build cumulative output for next round
            prev_output += f"\n\n### {phase['title']}\n{output}"

        return rounds

    def run_directed(self, queue: list) -> List[Dict[str, Any]]:
        """
        Run directed thinking on queued problems.
        5 phases per problem, iterative deepening.
        Returns list of round dicts.
        """
        if not queue:
            return []

        logger.info("=== DIRECTED THINKING (%d problems) ===", len(queue))
        all_rounds = []

        for item in queue:
            if self.should_stop():
                logger.info("Stopping directed thinking early")
                break

            problem = item.get("problem", str(item)) if isinstance(item, dict) else str(item)
            problem_context = item.get("context", "") if isinstance(item, dict) else ""
            logger.info("Problem: %s", problem[:80])

            prev_output = ""
            if problem_context:
                prev_output = f"Additional context: {problem_context}\n"

            for phase in DIRECTED_PHASES[:self.rounds_per_problem]:
                if self.should_stop():
                    break

                research_text = ""
                prompt = phase["prompt"].format(
                    context=self.context_text,
                    prev_output=prev_output[-3000:] if prev_output else "(first round)",
                    problem=problem,
                    research=research_text,
                )

                start = time.time()
                output = self.think_round(prompt, phase["name"], phase["title"])
                duration = time.time() - start

                if output is None:
                    continue

                # Research loop
                research_text = research_if_needed(output, enable=self.enable_research)
                if research_text:
                    self._research_queries += research_text.count("Search: ")
                    prompt_with_research = phase["prompt"].format(
                        context=self.context_text,
                        prev_output=prev_output[-3000:] if prev_output else "(first round)",
                        problem=problem,
                        research=research_text,
                    )
                    enriched = self.think_round(
                        prompt_with_research,
                        f"{phase['name']}_enriched",
                        f"{phase['title']} (with research)",
                    )
                    if enriched:
                        output = enriched
                        duration = time.time() - start

                round_data = {
                    "round": self._round_counter,
                    "phase": phase["name"],
                    "title": phase["title"],
                    "output": output,
                    "research": research_text,
                    "duration_s": duration,
                    "problem": problem,
                }
                all_rounds.append(round_data)
                write_round(self._round_counter, phase["name"], phase["title"],
                           output, research_text, duration)

                prev_output += f"\n\n### {phase['title']}\n{output}"

        return all_rounds

    @property
    def total_rounds(self) -> int:
        return self._round_counter

    @property
    def total_research_queries(self) -> int:
        return self._research_queries
