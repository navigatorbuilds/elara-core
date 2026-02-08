# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Elara Dream Mode — backwards compatibility re-export.

Real code lives in:
  daemon/dream_weekly.py   — weekly_dream, session/mood analysis
  daemon/dream_monthly.py  — monthly_dream, weekly trends, narrative threading
  daemon/dream_emotional.py — emotional_dream, monthly_emotional_dream, temperament
  daemon/dream_threads.py  — narrative_threads

Infrastructure in daemon/dream_core.py.
"""

import logging
from daemon.dream_core import (
    dream_status, dream_boot_check, read_latest_dream, EMOTIONAL_DIR,
)
from daemon.dream_weekly import weekly_dream
from daemon.dream_monthly import monthly_dream
from daemon.dream_emotional import emotional_dream, monthly_emotional_dream
from daemon.dream_threads import narrative_threads

logger = logging.getLogger("elara.dream")
