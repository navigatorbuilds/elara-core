"""
Elara Emotional State — re-export layer.

All logic lives in focused submodules:
- state_core:    constants, load/save, decay mechanics
- mood:          mood get/set/adjust, imprints, descriptions, emotions
- sessions:      episode/session lifecycle management
- temperament:   emotional growth system

This file re-exports everything so existing imports keep working unchanged.
"""

# --- Core (constants + internals used by submodules) ---
import logging
from daemon.state_core import (  # noqa: F401
    STATE_FILE, MOOD_JOURNAL_FILE, IMPRINT_ARCHIVE_FILE, TEMPERAMENT_LOG_FILE,
    TEMPERAMENT, FACTORY_TEMPERAMENT, TEMPERAMENT_MAX_DRIFT,
    DECAY_RATE, RESIDUE_DECAY_RATE, NOISE_SCALE,
    DEFAULT_STATE, SESSION_TYPE_RULES,
    _log_mood, _archive_imprint,
    _load_state, _save_state, _apply_time_decay, _decay_imprints,
)

# --- Mood ---
from daemon.mood import (  # noqa: F401
    get_mood, get_temperament, set_mood, adjust_mood,
    create_imprint, get_imprints, get_full_state, set_flag,
    describe_mood, describe_self, get_residue_summary,
    get_emotional_context_for_memory, get_current_emotions, get_session_arc,
    read_mood_journal, read_imprint_archive,
)

# --- Sessions ---
from daemon.sessions import (  # noqa: F401
    start_session, end_session,
    start_episode, end_episode,
    get_current_episode, add_project_to_session,
    get_session_type, set_session_type,
)

# --- Temperament ---
from daemon.temperament import (  # noqa: F401
    adapt_temperament, apply_emotional_growth,
    decay_temperament_toward_factory, reset_temperament,
    get_temperament_status,
)

logger = logging.getLogger("elara.state")
