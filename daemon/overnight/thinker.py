# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight Thinker — core thinking loop.

Runs exploratory (14 phases) and directed (5 phases per problem) thinking
using a local LLM via Ollama. Each round builds on previous output.

3D Cognition integration:
- 4 new phases produce structured JSON (model_check, prediction_check,
  model_build, crystallize)
- JSON is parsed and applied to models/predictions/principles
- Non-3D phases work exactly as before (narrative text output)
"""

import json
import logging
import re
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

    def __init__(self, context_text: str, config: dict, stop_flag=None,
                 context_dict: Optional[Dict[str, Any]] = None):
        self.context_text = context_text
        self.context_dict = context_dict or {}
        self.config = config
        self.model = config.get("think_model", "qwen2.5:32b")
        self.max_tokens = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.7)
        self.enable_research = config.get("enable_research", True)
        self.enable_3d = config.get("enable_3d_cognition", True)
        self.max_hours = config.get("max_hours", 6.0)
        self.stop_at = config.get("stop_at", "07:00")
        self.rounds_per_problem = config.get("rounds_per_problem", 5)

        self._start_time = datetime.now()
        self._stop_flag = stop_flag  # threading.Event for graceful stop
        self._round_counter = 0
        self._research_queries = 0

        # 3D Cognition tracking
        self._3d_stats = {
            "models_checked": 0,
            "models_created": 0,
            "models_updated": 0,
            "predictions_checked": 0,
            "predictions_created": 0,
            "principles_confirmed": 0,
            "principles_created": 0,
            "workflows_detected": 0,
            "workflows_confirmed": 0,
            "parse_failures": 0,
        }

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

    # ------------------------------------------------------------------
    # 3D Cognition context formatters
    # ------------------------------------------------------------------

    def _format_models_context(self) -> str:
        """Format cognitive models for LLM prompt."""
        models = self.context_dict.get("cognitive_models", [])
        if not models:
            return "(no models yet)"
        lines = []
        for m in models[:15]:
            lines.append(
                f"- [{m.get('model_id', '?')[:8]}] [{m.get('domain', '?')}] "
                f"{m.get('statement', '?')[:100]} "
                f"(conf={m.get('confidence', 0)}, checks={m.get('check_count', 0)}, "
                f"last_checked={m.get('last_checked', '?')[:10]})"
            )
        return "\n".join(lines)

    def _format_predictions_context(self) -> str:
        """Format pending predictions for LLM prompt."""
        preds = self.context_dict.get("predictions_pending", [])
        if not preds:
            return "(no pending predictions)"
        lines = []
        for p in preds[:10]:
            lines.append(
                f"- [{p.get('prediction_id', '?')[:8]}] {p.get('statement', '?')[:100]} "
                f"(conf={p.get('confidence', 0)}, deadline={p.get('deadline', '?')})"
            )
        return "\n".join(lines)

    def _format_prediction_accuracy(self) -> str:
        """Format prediction accuracy stats."""
        acc = self.context_dict.get("prediction_accuracy", {})
        if not acc or acc.get("total", 0) == 0:
            return "(no predictions tracked yet)"
        parts = [f"Total: {acc.get('total', 0)}, Checked: {acc.get('checked', 0)}"]
        if acc.get("accuracy") is not None:
            parts.append(f"Accuracy: {acc['accuracy']:.0%}")
        if acc.get("calibration") is not None:
            parts.append(f"Calibration: {acc['calibration']:+.0%}")
        return ", ".join(parts)

    def _format_principles_context(self) -> str:
        """Format principles for LLM prompt."""
        principles = self.context_dict.get("principles", [])
        if not principles:
            return "(no principles yet)"
        lines = []
        for p in principles[:10]:
            lines.append(
                f"- [{p.get('principle_id', '?')[:8]}] [{p.get('domain', '?')}] "
                f"{p.get('statement', '?')[:100]} "
                f"(conf={p.get('confidence', 0)}, confirmed={p.get('times_confirmed', 0)}x)"
            )
        return "\n".join(lines)

    def _format_workflows_context(self) -> str:
        """Format existing workflows for LLM prompt."""
        workflows = self.context_dict.get("workflows", [])
        if not workflows:
            return "(no workflows yet)"
        lines = []
        for w in workflows[:10]:
            steps = [s.get("action", "?")[:40] for s in w.get("steps", [])]
            lines.append(
                f"- [{w.get('workflow_id', '?')[:8]}] {w.get('name', '?')[:60]} "
                f"(domain={w.get('domain', '?')}, conf={w.get('confidence', 0)}, "
                f"matched={w.get('times_matched', 0)}x)\n"
                f"  Trigger: {w.get('trigger', '?')[:80]}\n"
                f"  Steps: {' → '.join(steps)}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 3D Cognition JSON processing
    # ------------------------------------------------------------------

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from LLM output, handling markdown code blocks."""
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding array or object boundaries
        for start_char, end_char in [('[', ']'), ('{', '}')]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass

        return None

    def _process_3d_output(self, phase_name: str, output: str):
        """Parse 3D phase JSON output and apply to storage."""
        if not self.enable_3d:
            return

        parsed = self._extract_json(output)
        if parsed is None:
            logger.warning("3D phase '%s' produced unparseable output", phase_name)
            self._3d_stats["parse_failures"] += 1
            return

        try:
            if phase_name == "model_check":
                self._apply_model_updates(parsed)
            elif phase_name == "prediction_check":
                self._apply_prediction_checks(parsed)
            elif phase_name == "model_build":
                self._apply_new_models(parsed)
            elif phase_name == "crystallize":
                self._apply_crystallization(parsed)
            elif phase_name == "workflow_detect":
                self._apply_workflow_detection(parsed)
        except Exception as e:
            logger.warning("3D apply failed for '%s': %s", phase_name, e)
            self._3d_stats["parse_failures"] += 1

    def _apply_model_updates(self, data):
        """Apply model evidence updates from model_check phase."""
        if not isinstance(data, list):
            return
        from daemon.models import add_evidence

        source_run = datetime.now().strftime("%Y-%m-%d")
        for update in data:
            try:
                model_id = update.get("model_id", "")
                direction = update.get("direction", "supports")
                evidence = update.get("evidence", "")
                if model_id and evidence:
                    add_evidence(model_id, evidence, source="overnight", direction=direction)
                    self._3d_stats["models_updated"] += 1
                    self._3d_stats["models_checked"] += 1
                    logger.info("  Model %s: %s (%s)", model_id[:8], direction, evidence[:60])
            except Exception as e:
                logger.warning("  Model update failed: %s", e)

    def _apply_prediction_checks(self, data):
        """Apply prediction checks and create new predictions."""
        if not isinstance(data, dict):
            return

        source_run = datetime.now().strftime("%Y-%m-%d")

        # Check existing predictions
        from daemon.predictions import check_prediction, make_prediction
        for check in data.get("checked", []):
            try:
                pred_id = check.get("prediction_id", "")
                status = check.get("status", "")
                actual = check.get("actual_outcome", "")
                lesson = check.get("lesson")
                if pred_id and status and actual:
                    check_prediction(pred_id, actual, status, lesson=lesson)
                    self._3d_stats["predictions_checked"] += 1
                    logger.info("  Prediction %s: %s", pred_id[:8], status)
            except Exception as e:
                logger.warning("  Prediction check failed: %s", e)

        # Create new predictions
        for new in data.get("new_predictions", []):
            try:
                statement = new.get("statement", "")
                confidence = new.get("confidence", 0.5)
                deadline = new.get("deadline", "")
                if statement:
                    make_prediction(
                        statement=statement,
                        confidence=confidence,
                        deadline=deadline,
                        source_run=source_run,
                        tags=["overnight"],
                    )
                    self._3d_stats["predictions_created"] += 1
                    logger.info("  New prediction: %s (conf=%.2f)", statement[:60], confidence)
            except Exception as e:
                logger.warning("  Prediction creation failed: %s", e)

    def _apply_new_models(self, data):
        """Create new cognitive models from model_build phase."""
        if not isinstance(data, list):
            return
        from daemon.models import create_model

        source_run = datetime.now().strftime("%Y-%m-%d")
        for model_data in data[:5]:  # Max 5 per run
            try:
                statement = model_data.get("statement", "")
                domain = model_data.get("domain", "general")
                confidence = model_data.get("confidence", 0.5)
                evidence = model_data.get("evidence", "")
                tags = model_data.get("tags", [])
                if statement:
                    create_model(
                        statement=statement,
                        domain=domain,
                        evidence_text=evidence,
                        confidence=confidence,
                        source_run=source_run,
                        tags=tags + ["overnight"],
                    )
                    self._3d_stats["models_created"] += 1
                    logger.info("  New model [%s]: %s (conf=%.2f)", domain, statement[:60], confidence)
            except Exception as e:
                logger.warning("  Model creation failed: %s", e)

    def _apply_crystallization(self, data):
        """Confirm existing principles and create new ones."""
        if not isinstance(data, dict):
            return

        source_run = datetime.now().strftime("%Y-%m-%d")

        # Confirm existing principles
        from daemon.principles import confirm_principle, create_principle
        for confirm in data.get("confirm", []):
            try:
                pid = confirm.get("principle_id", "")
                if pid:
                    confirm_principle(pid, run_date=source_run)
                    self._3d_stats["principles_confirmed"] += 1
                    logger.info("  Principle confirmed: %s", pid[:8])
            except Exception as e:
                logger.warning("  Principle confirmation failed: %s", e)

        # Create new principles
        for new in data.get("new_principles", [])[:2]:  # Max 2 per run
            try:
                statement = new.get("statement", "")
                domain = new.get("domain", "general")
                confidence = new.get("confidence", 0.5)
                if statement:
                    create_principle(
                        statement=statement,
                        domain=domain,
                        source_insights=[source_run],
                        confidence=confidence,
                        tags=["overnight"],
                    )
                    self._3d_stats["principles_created"] += 1
                    logger.info("  New principle [%s]: %s", domain, statement[:60])
            except Exception as e:
                logger.warning("  Principle creation failed: %s", e)

    def _apply_workflow_detection(self, data):
        """Create new workflows and confirm existing ones from workflow_detect phase."""
        if not isinstance(data, dict):
            return

        # Confirm existing workflows
        from daemon.workflows import confirm_workflow, create_workflow
        for confirm in data.get("confirm", []):
            try:
                wid = confirm.get("workflow_id", "")
                episode = confirm.get("episode_evidence", "")
                if wid:
                    confirm_workflow(wid, episode_id=episode)
                    self._3d_stats["workflows_confirmed"] += 1
                    logger.info("  Workflow confirmed: %s", wid[:8])
            except Exception as e:
                logger.warning("  Workflow confirmation failed: %s", e)

        # Create new workflows (max 3 per run)
        for new in data.get("new_workflows", [])[:3]:
            try:
                name = new.get("name", "")
                if not name:
                    continue
                steps = new.get("steps", [])
                workflow = create_workflow(
                    name=name,
                    domain=new.get("domain", "development"),
                    trigger=new.get("trigger", ""),
                    steps=steps,
                    confidence=new.get("confidence", 0.5),
                    tags=["overnight"],
                )
                self._3d_stats["workflows_detected"] += 1
                logger.info("  New workflow [%s]: %s (%d steps)",
                           new.get("domain", "?"), name[:60], len(steps))
            except Exception as e:
                logger.warning("  Workflow creation failed: %s", e)

    @property
    def cognition_summary(self) -> Dict[str, Any]:
        """Summary of 3D cognition actions taken during this run."""
        return dict(self._3d_stats)

    # ------------------------------------------------------------------
    # Main thinking loops
    # ------------------------------------------------------------------

    def run_exploratory(self) -> List[Dict[str, Any]]:
        """
        Run 8 exploratory phases. Each builds on previous output.
        Returns list of round dicts.
        """
        active_phases = EXPLORATORY_PHASES
        # Skip 3D phases if disabled
        if not self.enable_3d:
            active_phases = [p for p in EXPLORATORY_PHASES if not p.get("is_3d")]

        logger.info("=== EXPLORATORY THINKING (%d phases) ===", len(active_phases))
        rounds = []
        prev_output = ""

        for phase in active_phases:
            if self.should_stop():
                logger.info("Stopping exploratory thinking early (round %d/%d)",
                          len(rounds), len(active_phases))
                break

            is_3d = phase.get("is_3d", False)

            # Build prompt from template — 3D phases get extra context vars
            research_text = ""
            format_vars = {
                "context": self.context_text,
                "prev_output": prev_output[-3000:] if prev_output else "(first round)",
                "research": research_text,
            }
            if is_3d:
                format_vars.update({
                    "models_context": self._format_models_context(),
                    "predictions_context": self._format_predictions_context(),
                    "prediction_accuracy": self._format_prediction_accuracy(),
                    "principles_context": self._format_principles_context(),
                    "workflows_context": self._format_workflows_context(),
                })

            prompt = phase["prompt"].format(**format_vars)

            start = time.time()
            output = self.think_round(prompt, phase["name"], phase["title"])
            duration = time.time() - start

            if output is None:
                logger.warning("Phase '%s' produced no output, skipping", phase["name"])
                continue

            # 3D phases: parse JSON and apply changes
            if is_3d:
                self._process_3d_output(phase["name"], output)
            else:
                # Non-3D: check for research requests
                research_text = research_if_needed(output, enable=self.enable_research)
                if research_text:
                    self._research_queries += research_text.count("Search: ")
                    format_vars["research"] = research_text
                    prompt_with_research = phase["prompt"].format(**format_vars)
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
                "is_3d": is_3d,
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
