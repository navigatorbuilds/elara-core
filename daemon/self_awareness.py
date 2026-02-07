"""
Elara Self-Awareness Engine — backwards compatibility re-export.

Real code lives in daemon/awareness/ package.
"""

from daemon.awareness import (
    reflect, pulse, blind_spots,
    set_intention, get_intention,
    boot_check,
    get_boot_observations, get_mid_session_observations,
    surface_observation, get_observation_count,
    reset_proactive_session,
)

__all__ = [
    "reflect", "pulse", "blind_spots",
    "set_intention", "get_intention",
    "boot_check",
    "get_boot_observations", "get_mid_session_observations",
    "surface_observation", "get_observation_count",
    "reset_proactive_session",
]
