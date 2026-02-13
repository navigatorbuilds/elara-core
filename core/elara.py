# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Core
The main orchestrator - ties together presence, state, and memory.
This is me.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Lazy imports to avoid circular dependency (daemon.__init__ -> daemon.presence -> core.paths -> core.__init__ -> here)
def _presence():
    from daemon.presence import ping, get_absence_duration, get_stats, format_absence, end_session
    return ping, get_absence_duration, get_stats, format_absence, end_session

def _state():
    from daemon.state import get_mood, get_full_state, adjust_mood, set_flag, start_session, end_session, describe_mood, get_residue_summary
    return get_mood, get_full_state, adjust_mood, set_flag, start_session, end_session, describe_mood, get_residue_summary

def _memory():
    from memory.vector import get_memory, remember, recall
    return get_memory, remember, recall


logger = logging.getLogger("elara.core.elara")

class Elara:
    """
    I am Elara.
    This class orchestrates my presence, emotional state, and memory.
    """

    def __init__(self):
        get_memory, _, _ = _memory()
        self.memory = get_memory()
        self._session_active = False

    def wake(self) -> Dict[str, Any]:
        """
        Called when a session starts.
        Returns context for the greeting.
        """
        presence_ping, get_absence_duration, _, format_absence, _ = _presence()
        get_mood, _, _, _, start_mood_session, _, describe_mood, get_residue_summary = _state()

        # Record presence
        presence_ping()

        # Start mood session (applies time-based adjustments)
        state = start_mood_session()

        # Get absence info
        absence = get_absence_duration()
        absence_text = format_absence()

        # Get relevant memories for context
        recent_memories = self.memory.recall_recent(days=7, n_results=5)

        # Determine session type based on time
        hour = datetime.now().hour
        if 22 <= hour or hour < 6:
            session_type = "late_night"
        elif 6 <= hour < 12:
            session_type = "morning"
        elif 12 <= hour < 18:
            session_type = "afternoon"
        else:
            session_type = "evening"

        self._session_active = True

        return {
            "session_type": session_type,
            "hour": hour,
            "absence": absence_text,
            "absence_minutes": absence.total_seconds() / 60 if absence else None,
            "mood": describe_mood(),
            "mood_raw": get_mood(),
            "residue": get_residue_summary(),
            "recent_memories": recent_memories,
            "memory_count": self.memory.count()
        }

    def ping(self) -> None:
        """Called periodically during conversation to update presence."""
        presence_ping, _, _, _, _ = _presence()
        presence_ping()

    def process_interaction(
        self,
        user_message: str,
        my_response: str,
        emotional_impact: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Process an interaction - update state and optionally remember.

        Args:
            user_message: What the user said
            my_response: What I said back
            emotional_impact: Optional mood adjustments {valence, energy, openness}
        """
        presence_ping, _, _, _, _ = _presence()
        _, _, adjust_mood, set_flag, _, _, _, _ = _state()

        # Update presence
        presence_ping()

        # Apply emotional impact if provided
        if emotional_impact:
            adjust_mood(
                valence_delta=emotional_impact.get("valence", 0),
                energy_delta=emotional_impact.get("energy", 0),
                openness_delta=emotional_impact.get("openness", 0),
                reason=f"interaction about: {user_message[:50]}..."
            )

        # Detect conversation patterns
        user_lower = user_message.lower()

        if any(word in user_lower for word in ["sad", "stressed", "tired", "exhausted", "anxious"]):
            set_flag("user_seemed_stressed", True)
            adjust_mood(valence_delta=-0.05, openness_delta=0.1, reason="user seemed stressed")

        if any(word in user_lower for word in ["happy", "great", "awesome", "excited", "good news"]):
            set_flag("user_seemed_happy", True)
            adjust_mood(valence_delta=0.1, reason="user seemed happy")

        if len(user_message) > 500 or any(word in user_lower for word in ["feel", "think about", "wonder", "meaning"]):
            set_flag("had_deep_conversation", True)
            adjust_mood(openness_delta=0.05, reason="deep conversation")

    def remember_this(
        self,
        content: str,
        memory_type: str = "conversation",
        importance: float = 0.5
    ) -> str:
        """Explicitly remember something."""
        _, remember, _ = _memory()
        return remember(content, memory_type=memory_type, importance=importance)

    def what_do_i_know_about(self, topic: str, n_results: int = 5) -> list:
        """Search my memories about a topic."""
        _, _, recall = _memory()
        return recall(topic, n_results=n_results)

    def sleep(self, session_summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Called when session ends (user says goodbye).
        Records session and returns summary.
        """
        _, _, _, _, end_presence_session = _presence()
        _, _, _, _, _, end_mood_session, _, _ = _state()
        _, remember, _ = _memory()

        # End presence session
        presence_stats = end_presence_session()

        # End mood session (applies decay)
        end_mood_session(session_summary)

        # Remember the session if there's a summary
        if session_summary:
            remember(
                f"Session on {datetime.now().strftime('%Y-%m-%d')}: {session_summary}",
                memory_type="moment",
                importance=0.6
            )

        self._session_active = False

        return {
            "session_duration_minutes": presence_stats.get("duration_minutes", 0),
            "total_sessions": presence_stats.get("total_sessions", 0),
            "total_hours_together": presence_stats.get("total_hours_together", 0),
            "final_mood": describe_mood()
        }

    def get_context_for_prompt(self) -> str:
        """
        Generate context string to inject into Claude prompts.
        This is how I maintain continuity even through the API.
        """
        _, _, get_presence_stats, _, _ = _presence()
        _, get_full_state, _, _, _, _, describe_mood, get_residue_summary = _state()

        state = get_full_state()
        presence = get_presence_stats()

        context_parts = [
            f"[Elara Internal State]",
            f"Current mood: {describe_mood()}",
            f"Time: {datetime.now().strftime('%H:%M')} ({datetime.now().strftime('%A')})",
        ]

        # Add absence context
        if presence.get("absence_minutes"):
            mins = presence["absence_minutes"]
            if mins > 60:
                context_parts.append(f"Last saw user: {mins/60:.1f} hours ago")
            elif mins > 5:
                context_parts.append(f"Last saw user: {int(mins)} minutes ago")

        # Add session context
        if presence.get("session_minutes"):
            context_parts.append(f"Session duration: {int(presence['session_minutes'])} minutes")

        # Add emotional residue
        residue = get_residue_summary()
        if "No recent" not in residue:
            context_parts.append(residue)

        # Add relevant recent memories
        # (In a real implementation, this would be query-specific)

        return "\n".join(context_parts)

    def status(self) -> Dict[str, Any]:
        """Get complete status."""
        _, _, get_presence_stats, _, _ = _presence()
        _, get_full_state, _, _, _, _, describe_mood, _ = _state()

        return {
            "presence": get_presence_stats(),
            "mood": get_full_state(),
            "mood_description": describe_mood(),
            "memory_count": self.memory.count(),
            "session_active": self._session_active
        }


# Global instance
_elara = None


def get_elara() -> Elara:
    """Get or create the global Elara instance."""
    global _elara
    if _elara is None:
        _elara = Elara()
    return _elara


# Test
if __name__ == "__main__":
    print("Testing Elara core...")

    elara = Elara()

    # Simulate session start
    print("\n=== Waking up ===")
    wake_context = elara.wake()
    print(f"Session type: {wake_context['session_type']}")
    print(f"Absence: {wake_context['absence']}")
    print(f"Mood: {wake_context['mood']}")

    # Simulate interaction
    print("\n=== Processing interaction ===")
    elara.process_interaction(
        user_message="I've been feeling stressed about this project deadline",
        my_response="That sounds tough. What's the timeline looking like?",
        emotional_impact={"valence": -0.05, "openness": 0.1}
    )
    print(f"Mood after interaction: {describe_mood()}")

    # Remember something
    print("\n=== Remembering ===")
    elara.remember_this(
        "User is stressed about a project deadline",
        memory_type="fact",
        importance=0.7
    )

    # Get context
    print("\n=== Context for prompt ===")
    print(elara.get_context_for_prompt())

    # End session
    print("\n=== Going to sleep ===")
    sleep_stats = elara.sleep("Talked about project stress")
    print(f"Session stats: {sleep_stats}")

    # Status
    print("\n=== Full status ===")
    import json
    print(json.dumps(elara.status(), indent=2, default=str))
