# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Dream Mode — Narrative Threading.

Groups episodes into story arcs (threads) by project and temporal proximity.
"""

import logging
import json
from datetime import datetime
from typing import List

from daemon.schemas import atomic_write_json

from daemon.dream_core import (
    _ensure_dirs, _load_status, _save_status, THREADS_DIR,
)


logger = logging.getLogger("elara.dream_threads")

def narrative_threads() -> dict:
    """Group episodes into story arcs (threads)."""
    _ensure_dirs()
    from memory.episodic import get_episodic
    episodic = get_episodic()

    all_episodes = episodic.get_recent_episodes(n=200)
    all_episodes.reverse()

    project_episodes = {}
    for ep in all_episodes:
        for proj in ep.get("projects", []):
            if proj not in project_episodes:
                project_episodes[proj] = []
            project_episodes[proj].append(ep)

    threads = []

    for project, eps in project_episodes.items():
        if not eps:
            continue

        current_thread_eps = [eps[0]]
        sub_threads = []

        for i in range(1, len(eps)):
            try:
                prev_end = datetime.fromisoformat(eps[i - 1].get("ended") or eps[i - 1].get("started", ""))
                curr_start = datetime.fromisoformat(eps[i].get("started", ""))
                gap_hours = (curr_start - prev_end).total_seconds() / 3600
                if gap_hours > 48:
                    sub_threads.append(current_thread_eps)
                    current_thread_eps = [eps[i]]
                else:
                    current_thread_eps.append(eps[i])
            except (ValueError, TypeError):
                current_thread_eps.append(eps[i])

        sub_threads.append(current_thread_eps)

        for thread_eps in sub_threads:
            if not thread_eps:
                continue

            episode_ids = [ep["id"] for ep in thread_eps]
            first_date = thread_eps[0].get("started", "")[:10]
            last_date = thread_eps[-1].get("ended") or thread_eps[-1].get("started", "")
            last_date = last_date[:10] if last_date else first_date

            try:
                last_end = datetime.fromisoformat(thread_eps[-1].get("ended") or thread_eps[-1].get("started", ""))
                days_since = (datetime.now() - last_end).days
                if days_since > 14: status = "abandoned"
                elif days_since > 7: status = "stalled"
                else: status = "active"
            except (ValueError, TypeError):
                status = "unknown"

            key_events = []
            for ep in thread_eps:
                for m in ep.get("milestones", []):
                    if m.get("importance", 0) >= 0.7:
                        key_events.append(m["event"])
                for d in ep.get("decisions", []):
                    key_events.append(f"Decision: {d['what']}")

            total_minutes = sum(ep.get("duration_minutes") or 0 for ep in thread_eps)
            name = _generate_thread_name(project, thread_eps, key_events)

            threads.append({
                "name": name, "project": project, "episode_ids": episode_ids,
                "episode_count": len(episode_ids),
                "date_range": f"{first_date} to {last_date}",
                "total_minutes": total_minutes, "status": status,
                "key_events": key_events[:10],
                "summary": _generate_thread_summary(project, thread_eps, key_events, total_minutes, status),
            })

    threads.sort(key=lambda t: t.get("date_range", "").split(" to ")[-1], reverse=True)

    result = {"generated": datetime.now().isoformat(), "thread_count": len(threads), "threads": threads}

    threads_file = THREADS_DIR / "latest.json"
    atomic_write_json(threads_file, result)

    for thread in threads:
        safe_name = thread["name"].lower().replace(" ", "-").replace("/", "-")[:50]
        thread_file = THREADS_DIR / f"{safe_name}.json"
        atomic_write_json(thread_file, thread)

    status = _load_status()
    status["last_threads"] = datetime.now().isoformat()
    _save_status(status)

    return result


def _generate_thread_name(project: str, episodes: List[dict], key_events: List[str]) -> str:
    n = len(episodes)
    if key_events:
        return f"{project}: {key_events[0][:40]}"
    first_date = episodes[0].get("started", "")[:10]
    return f"{project} ({first_date}, {n} sessions)"


def _generate_thread_summary(
    project: str, episodes: List[dict], key_events: List[str],
    total_minutes: int, status: str
) -> str:
    n = len(episodes)
    parts = [f"{n} session{'s' if n != 1 else ''}, {total_minutes} minutes total."]
    if key_events:
        parts.append(f"Key events: {'; '.join(key_events[:3])}.")
    if status == "active": parts.append("Currently active.")
    elif status == "stalled": parts.append("Stalled — no activity in 7+ days.")
    elif status == "abandoned": parts.append("Abandoned — no activity in 14+ days.")
    return " ".join(parts)
