# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Self-Awareness Engine — package re-exports.

Five lenses, one growth loop:
- reflect()     — "Who have I been?"
- pulse()       — "How are we doing?"
- blind_spots() — "What am I missing?"
- intention()   — "What do I want to change?"
- proactive     — "What should I notice?"

External code imports from daemon.self_awareness (backwards-compat layer)
or directly from daemon.awareness.
"""

from daemon.awareness.reflect import reflect
from daemon.awareness.pulse import pulse
from daemon.awareness.blind_spots import blind_spots
from daemon.awareness.intention import set_intention, get_intention
from daemon.awareness.boot import boot_check
from daemon.awareness.proactive import (
    get_boot_observations,
    get_mid_session_observations,
    surface_observation,
    get_observation_count,
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
