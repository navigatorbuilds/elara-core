"""
Elara Dream Mode — re-export layer.

All logic lives in focused submodules:
- dream_core:       constants, data gathering, status, utilities
- dream_weekly:     weekly dream + session/mood analysis
- dream_monthly:    monthly dream + narrative threading
- dream_emotional:  emotional dreams, temperament growth, tone hints

This file re-exports everything so existing imports keep working unchanged.
"""

# --- Core (constants + status) ---
from daemon.dream_core import (  # noqa: F401
    EMOTIONAL_DIR,
    dream_status, dream_boot_check, read_latest_dream,
)

# --- Weekly ---
from daemon.dream_weekly import weekly_dream  # noqa: F401

# --- Monthly ---
from daemon.dream_monthly import monthly_dream, narrative_threads  # noqa: F401

# --- Emotional ---
from daemon.dream_emotional import emotional_dream, monthly_emotional_dream  # noqa: F401
