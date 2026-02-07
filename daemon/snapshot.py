"""
Elara Snapshot — Centralized state-of-the-world object.

Single entry point for "what's going on right now?" instead of
self_awareness.py and dream.py each reaching into 6+ modules.

Reduces coupling, makes testing easier, provides consistent view.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("elara.snapshot")


def get_snapshot() -> Dict[str, Any]:
    """
    Produce a complete state-of-the-world snapshot.

    Returns dict with all current state, safely handling
    unavailable modules.
    """
    now = datetime.now()
    snapshot = {
        "timestamp": now.isoformat(),
        "mood": _get_mood(),
        "presence": _get_presence(),
        "episode": _get_episode(),
        "goals": _get_goals(),
        "corrections": _get_corrections(),
        "business": _get_business(),
        "memories": _get_memory_stats(),
        "conversations": _get_conversation_stats(),
        "synthesis": _get_synthesis(),
        "briefing": _get_briefing(),
        "handoff": _get_handoff(),
    }

    return snapshot


def _get_mood() -> Dict[str, Any]:
    """Current mood state."""
    try:
        from daemon.state import get_mood, get_state
        mood = get_mood()
        state = get_state()
        return {
            "valence": mood.get("valence", 0.5),
            "energy": mood.get("energy", 0.5),
            "openness": mood.get("openness", 0.5),
            "description": mood.get("description", ""),
            "mode": state.get("mode"),
            "allostatic_load": state.get("allostatic_load", 0.0),
        }
    except Exception as e:
        logger.debug(f"Mood unavailable: {e}")
        return {"error": str(e)}


def _get_presence() -> Dict[str, Any]:
    """Presence and session info."""
    try:
        from daemon.presence import get_presence
        return get_presence()
    except Exception as e:
        logger.debug(f"Presence unavailable: {e}")
        return {"error": str(e)}


def _get_episode() -> Optional[Dict[str, Any]]:
    """Current active episode."""
    try:
        from memory.episodic import get_current_episode
        ep = get_current_episode()
        if ep:
            return {
                "id": ep.get("episode_id"),
                "type": ep.get("type"),
                "started": ep.get("started"),
                "projects": ep.get("projects", []),
                "milestone_count": len(ep.get("milestones", [])),
                "decision_count": len(ep.get("decisions", [])),
            }
        return None
    except Exception as e:
        logger.debug(f"Episode unavailable: {e}")
        return None


def _get_goals() -> Dict[str, Any]:
    """Goal summary."""
    try:
        from daemon.goals import list_goals
        goals = list_goals()
        active = [g for g in goals if g.get("status") == "active"]
        stalled = [g for g in goals if g.get("status") == "stalled"]
        done = [g for g in goals if g.get("status") == "done"]
        return {
            "total": len(goals),
            "active": len(active),
            "stalled": len(stalled),
            "done": len(done),
            "active_titles": [g.get("title", "") for g in active[:5]],
        }
    except Exception as e:
        logger.debug(f"Goals unavailable: {e}")
        return {"error": str(e)}


def _get_corrections() -> Dict[str, Any]:
    """Corrections summary."""
    try:
        from daemon.corrections import get_all
        corrections = get_all()
        return {
            "total": len(corrections),
            "types": {
                "tendency": sum(1 for c in corrections if c.get("correction_type") == "tendency"),
                "technical": sum(1 for c in corrections if c.get("correction_type") == "technical"),
            },
        }
    except Exception as e:
        logger.debug(f"Corrections unavailable: {e}")
        return {"error": str(e)}


def _get_business() -> Dict[str, Any]:
    """Business ideas summary."""
    try:
        from daemon.business import get_idea_stats
        return get_idea_stats()
    except Exception as e:
        logger.debug(f"Business unavailable: {e}")
        return {"error": str(e)}


def _get_memory_stats() -> Dict[str, Any]:
    """Semantic memory stats."""
    try:
        from memory.vector import VectorMemory
        vm = VectorMemory()
        count = vm.collection.count() if vm.collection else 0
        return {"count": count}
    except Exception as e:
        logger.debug(f"Memory unavailable: {e}")
        return {"error": str(e)}


def _get_conversation_stats() -> Dict[str, Any]:
    """Conversation memory stats."""
    try:
        from memory.conversations import get_conversations
        conv = get_conversations()
        return {"count": conv.count()}
    except Exception as e:
        logger.debug(f"Conversations unavailable: {e}")
        return {"error": str(e)}


def _get_synthesis() -> Dict[str, Any]:
    """Synthesis (recurring ideas) summary."""
    try:
        from daemon.synthesis import get_synthesis_stats
        return get_synthesis_stats()
    except Exception as e:
        logger.debug(f"Synthesis unavailable: {e}")
        return {"error": str(e)}


def _get_briefing() -> Dict[str, Any]:
    """Briefing summary."""
    try:
        from daemon.briefing import get_stats
        return get_stats()
    except Exception as e:
        logger.debug(f"Briefing unavailable: {e}")
        return {"error": str(e)}


def _get_handoff() -> Optional[Dict[str, Any]]:
    """Last handoff data."""
    try:
        from daemon.handoff import load_handoff
        return load_handoff()
    except Exception as e:
        logger.debug(f"Handoff unavailable: {e}")
        return None
