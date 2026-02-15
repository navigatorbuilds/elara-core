# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Dream mode tools — weekly, monthly, and emotional pattern discovery.

Consolidated from 3 → 2 tools.
"""

from elara_mcp._app import tool
from daemon.dream import (
    weekly_dream, monthly_dream, emotional_dream,
    dream_status, read_latest_dream,
)


@tool()
def elara_dream(dream_type: str = "weekly") -> str:
    """
    Run dream mode — pattern discovery across sessions.

    Weekly: project momentum, session patterns, mood trends, goal progress.
    Also runs self-reflection alongside.

    Monthly: big picture + narrative threading. What shipped, what stalled,
    time allocation, trend lines.

    Emotional: processes drift sessions, adjusts temperament, calibrates tone.
    Runs automatically with weekly/monthly, but can be triggered standalone.

    Args:
        dream_type: "weekly", "monthly", or "emotional"

    Returns:
        Dream report summary
    """
    if dream_type == "weekly":
        report = weekly_dream()

        emo = report.get("emotional", {})
        emo_line = ""
        if emo and not emo.get("error"):
            traj = emo.get("trajectory", "stable")
            hints = emo.get("tone_hints", [])
            adj = emo.get("temperament_adjustments", {})
            emo_parts = [f"Emotional: trajectory={traj}"]
            if adj:
                emo_parts.append(f"temperament: {', '.join(f'{k} {v:+.3f}' for k, v in adj.items())}")
            if hints:
                emo_parts.append(f"tone: {hints[0]}")
            emo_line = "\n" + " | ".join(emo_parts) + "\n"

        return (
            f"[Weekly Dream — {report['id']}]\n\n"
            f"{report['summary']}\n\n"
            f"Key milestones: {len(report.get('key_milestones', []))}\n"
            f"Decisions: {len(report.get('decisions', []))}\n\n"
            f"Reflection: {report.get('reflection', {}).get('portrait', 'none')}\n"
            f"{emo_line}\n"
            f"Saved to: ~/.claude/elara-dreams/weekly/{report['id']}.json"
        )
    elif dream_type == "monthly":
        report = monthly_dream()

        threads = report.get("narrative_threads", {})
        thread_lines = []
        for t in threads.get("threads", [])[:10]:
            thread_lines.append(f"  [{t['status']}] {t['name']} ({t['episodes']}s, {t['minutes']}m)")

        emo = report.get("emotional", {})
        emo_line = ""
        if emo and not emo.get("error"):
            emo_line = f"\nEmotional trajectory: {emo.get('dominant_trajectory', '?')}\n"

        return (
            f"[Monthly Dream — {report['id']}]\n\n"
            f"{report['summary']}\n\n"
            f"--- Story Arcs ---\n"
            f"{chr(10).join(thread_lines) if thread_lines else 'No threads found.'}\n"
            f"{emo_line}\n"
            f"Saved to: ~/.claude/elara-dreams/monthly/{report['id']}.json"
        )
    elif dream_type == "emotional":
        report = emotional_dream()

        growth = report.get("temperament_growth", {})
        adj = growth.get("adjustments", {})
        reasons = growth.get("reasons", [])
        hints = report.get("tone_hints", [])
        rel = report.get("relationship", {})

        lines = [f"[Emotional Dream — {report['id']}]", ""]
        lines.append(report.get("summary", "No summary."))
        lines.append("")

        if adj:
            lines.append("Temperament adjustments:")
            for dim, val in adj.items():
                lines.append(f"  {dim}: {val:+.4f}")
        else:
            lines.append("No temperament adjustments.")

        if reasons:
            lines.append(f"\nReasons: {'; '.join(reasons)}")

        if growth.get("intention_conflict"):
            lines.append(f"\n⚠ {growth['intention_conflict']}")

        if hints:
            lines.append(f"\nTone hints:")
            for h in hints:
                lines.append(f"  - {h}")

        lines.append(f"\nRelationship: {rel.get('trajectory', '?')} (drift ratio: {rel.get('drift_ratio', 0):.0%})")

        drift = growth.get("drift_from_factory", {})
        if drift:
            lines.append(f"Temperament drift from factory: {', '.join(f'{k} {v:+.3f}' for k, v in drift.items())}")

        lines.append(f"\nSaved to: ~/.claude/elara-dreams/emotional/{report['id']}.json")

        return "\n".join(lines)
    else:
        return f"Unknown dream type '{dream_type}'. Use 'weekly', 'monthly', or 'emotional'."


@tool()
def elara_dream_info(action: str = "status", dream_type: str = "weekly") -> str:
    """
    Check dream schedule or read the latest dream report.

    Args:
        action: "status" for schedule/overdue info, "read" for latest report
        dream_type: For read: "weekly", "monthly", "threads", "emotional", or "monthly_emotional"

    Returns:
        Dream status or report content
    """
    if action == "read":
        report = read_latest_dream(dream_type)

        if not report:
            return f"No {dream_type} dream found. Run elara_dream first."

        if dream_type == "threads":
            threads = report.get("threads", [])
            lines = [f"[Narrative Threads — {report.get('generated', '?')[:10]}]", f"{len(threads)} story arcs:", ""]
            for t in threads:
                status_icon = {"active": ">>", "stalled": "||", "abandoned": "xx", "unknown": "??"}.get(t["status"], "??")
                lines.append(f"  {status_icon} {t['name']}")
                lines.append(f"     {t['episode_count']} sessions, {t['total_minutes']}m | {t['date_range']}")
                lines.append(f"     {t['summary']}")
                lines.append("")
            return "\n".join(lines)
        elif dream_type in ("emotional", "monthly_emotional"):
            generated = report.get("generated", "?")[:10]
            lines = [f"[{dream_type.replace('_', ' ').title()} Dream — {report.get('id', '?')} (generated {generated})]", ""]
            lines.append(report.get("summary", "No summary."))

            growth = report.get("temperament_growth", {}) or report.get("temperament_evolution", {})
            drift = growth.get("drift_from_factory", {}) or growth.get("total_drift", {})
            if drift:
                lines.append(f"\nTemperament drift: {', '.join(f'{k} {v:+.3f}' for k, v in drift.items())}")

            hints = report.get("tone_hints", [])
            if hints:
                lines.append("\nTone hints:")
                for h in hints:
                    lines.append(f"  - {h}")

            rel = report.get("relationship", {}) or report.get("relationship_evolution", {})
            traj = rel.get("trajectory", rel.get("dominant", "?"))
            lines.append(f"\nRelationship trajectory: {traj}")

            return "\n".join(lines)
        else:
            report_id = report.get("id", "unknown")
            summary = report.get("summary", "No summary.")
            generated = report.get("generated", "?")[:10]

            lines = [f"[{dream_type.title()} Dream — {report_id} (generated {generated})]", "", summary]

            if dream_type == "weekly":
                momentum = report.get("project_momentum", [])
                if momentum:
                    lines.append("\nProject Momentum:")
                    for p in momentum:
                        icon = {"active": ">>", "stalled": "||", "abandoned": "xx", "inactive": "--"}.get(p["status"], "??")
                        lines.append(f"  {icon} {p['project']}: {p['sessions']}s, {p['minutes']}m ({p['status']})")

            if dream_type == "monthly":
                alloc = report.get("time_allocation", {})
                if alloc:
                    lines.append("\nTime Allocation:")
                    for proj, info in alloc.items():
                        lines.append(f"  {proj}: {info['percent']}% ({info['minutes']}m)")

                threads = report.get("narrative_threads", {})
                if threads.get("threads"):
                    lines.append(f"\nStory Arcs ({threads['total']} total):")
                    for t in threads["threads"][:10]:
                        lines.append(f"  [{t['status']}] {t['name']}")

            return "\n".join(lines)

    # status (default)
    ds = dream_status()

    lines = ["[Dream Status]"]

    if ds["last_weekly"]:
        age = ds["weekly_age_days"]
        overdue = " ** OVERDUE **" if ds["weekly_overdue"] else ""
        lines.append(f"  Weekly: last run {ds['last_weekly'][:10]} ({age}d ago){overdue}")
    else:
        lines.append("  Weekly: never run ** OVERDUE **")

    if ds["last_monthly"]:
        age = ds["monthly_age_days"]
        overdue = " ** OVERDUE **" if ds["monthly_overdue"] else ""
        lines.append(f"  Monthly: last run {ds['last_monthly'][:10]} ({age}d ago){overdue}")
    else:
        lines.append("  Monthly: never run ** OVERDUE **")

    if ds["last_threads"]:
        lines.append(f"  Threads: last run {ds['last_threads'][:10]}")
    else:
        lines.append("  Threads: never run")

    if ds.get("last_emotional"):
        age = ds.get("emotional_age_days")
        lines.append(f"  Emotional: last run {ds['last_emotional'][:10]} ({age}d ago)")
    else:
        lines.append("  Emotional: never run")

    lines.append(f"  Total dreams: {ds['weekly_count']} weekly, {ds['monthly_count']} monthly, {ds.get('emotional_count', 0)} emotional")

    return "\n".join(lines)
