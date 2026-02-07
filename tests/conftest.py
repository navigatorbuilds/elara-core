"""Test configuration — ensure project root is on sys.path."""

import sys
from pathlib import Path

# Add project root to sys.path so `from daemon.X import Y` works
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
