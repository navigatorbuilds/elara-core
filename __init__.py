# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Core
A framework for giving Claude persistent presence, emotional state, and semantic memory.
"""

try:
    from importlib.metadata import version
    __version__ = version("elara-core")
except Exception:
    __version__ = "0.17.0"

try:
    from .core.elara import Elara, get_elara
except ImportError:
    pass  # Direct import (e.g., pytest) — submodules still work via daemon.*
