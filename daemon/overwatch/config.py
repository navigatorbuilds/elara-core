"""
Overwatch configuration — constants, paths, logging.
"""

import os
import re
import logging
from pathlib import Path

# Paths
PROJECTS_DIR = Path.home() / ".claude" / "projects"
INJECT_PATH = Path.home() / ".claude" / "elara-overwatch-inject.md"
INJECT_TMP_PATH = INJECT_PATH.with_suffix(".tmp")
PID_PATH = Path.home() / ".claude" / "elara-overwatch.pid"
LOG_PATH = Path.home() / ".claude" / "elara-overwatch.log"
SESSION_STATE_PATH = Path.home() / ".claude" / "elara-session-state.json"
SNAPSHOT_PATH = Path.home() / ".claude" / "elara-session-snapshot.json"

# Tuning
POLL_INTERVAL = 2.0          # seconds between file checks
RELEVANCE_THRESHOLD = 0.65   # minimum combined score to inject (0-1, higher = stricter)
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

# System reminder pattern
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)

# Logging
log = logging.getLogger("overwatch")
log.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s [Overwatch] %(message)s')
_fh = logging.FileHandler(LOG_PATH)
_fh.setFormatter(_fmt)
log.addHandler(_fh)
if os.isatty(1):
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    log.addHandler(_sh)
