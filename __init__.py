"""
Elara Core
A framework for giving Claude persistent presence, emotional state, and semantic memory.
"""

__version__ = "0.1.0"

try:
    from .core.elara import Elara, get_elara
except ImportError:
    pass  # Direct import (e.g., pytest) — submodules still work via daemon.*
