# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight config — constants, paths, logging setup.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from core.paths import get_paths

_p = get_paths()

# Directories
OVERNIGHT_DIR = _p.overnight_dir
PID_FILE = _p.overnight_pid
LOG_FILE = _p.overnight_log
CONFIG_FILE = _p.overnight_config
QUEUE_FILE = _p.overnight_queue
LATEST_FINDINGS = _p.overnight_latest

# Defaults
DEFAULT_CONFIG = {
    "max_hours": 6.0,
    "stop_at": "07:00",
    "think_model": "qwen2.5:32b",
    "mode": "auto",
    "rounds_per_problem": 5,
    "max_tokens": 2048,
    "temperature": 0.7,
    "enable_research": True,
}


def setup_logging() -> logging.Logger:
    """Configure overnight-specific logging to file + stderr."""
    OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("elara.overnight")
    logger.setLevel(logging.INFO)

    # File handler — append to overnight.log
    fh = logging.FileHandler(str(LOG_FILE), mode="a")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Stderr handler for when running in foreground
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(sh)

    return logger


def load_config() -> dict:
    """Load overnight config, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text())
            config.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def load_queue() -> list:
    """Load the directed-thinking queue."""
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def today_dir() -> Path:
    """Return today's output directory, creating it if needed."""
    d = OVERNIGHT_DIR / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d
