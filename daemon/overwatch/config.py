"""
Overwatch configuration — constants, paths, logging.
"""

import os
import re
import logging
from pathlib import Path

from core.paths import get_paths

# Paths
_p = get_paths()
PROJECTS_DIR = _p.claude_projects
INJECT_PATH = _p.overwatch_inject
INJECT_TMP_PATH = INJECT_PATH.with_suffix(".tmp")
PID_PATH = _p.overwatch_pid
LOG_PATH = _p.overwatch_log
SESSION_STATE_PATH = _p.session_state
SNAPSHOT_PATH = _p.session_snapshot

# Tuning
POLL_INTERVAL = 2.0          # seconds between file checks
RELEVANCE_THRESHOLD = 0.58   # minimum combined score to inject (cosine on conversations clusters 0.5-0.7)
COOLDOWN_SECONDS = 600       # 10 min cooldown per topic cluster
MAX_INJECTIONS_PER_CHECK = 3 # max results per injection
EVENT_THRESHOLD = 0.55       # lower threshold for event-triggered searches
HEARTBEAT_TIMEOUT = 300      # 5 min — exit if JSONL stale (session likely dead)
TWENTY_FOUR_HOURS = 86400    # seconds — downweight recent results to prevent feedback loops
RECENT_DOWNWEIGHT = 0.5      # multiply score by this for results < 24h old
OVERDUE_BOOST = 0.15         # score boost for results matching overdue items

# Micro-ingestion
MICRO_INGEST_EXCHANGES = 5   # ingest every N exchanges
MICRO_INGEST_SECONDS = 600   # or every N seconds, whichever first

# Session snapshot
SNAPSHOT_INTERVAL = 1200     # 20 min between snapshots
SNAPSHOT_MIN_EXCHANGES = 3   # need at least 3 exchanges before first snapshot

# Event detection keywords
TASK_COMPLETE_WORDS = {"done", "built", "fixed", "shipped", "committed", "deployed", "pushed", "created", "finished"}
WINDING_DOWN_WORDS = {"anything else", "that's it", "what else", "done for", "calling it", "bye", "goodnight", "heading out"}

# Patterns to strip from text before processing
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)
OVERWATCH_CONTEXT_RE = re.compile(r'<overwatch-context>.*?</overwatch-context>', re.DOTALL)

# Logging
log = logging.getLogger("overwatch")
log.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s [Overwatch] %(message)s')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_fh = logging.FileHandler(LOG_PATH)
_fh.setFormatter(_fmt)
log.addHandler(_fh)
if os.isatty(1):
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    log.addHandler(_sh)
