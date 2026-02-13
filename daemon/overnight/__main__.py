# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Entry point: python3 -m daemon.overnight"""

import sys
from daemon.overnight.config import setup_logging

logger = setup_logging()

mode = None
for arg in sys.argv[1:]:
    if arg.startswith("--mode="):
        mode = arg.split("=", 1)[1]
    elif arg == "--mode" and sys.argv.index(arg) + 1 < len(sys.argv):
        mode = sys.argv[sys.argv.index(arg) + 1]

from daemon.overnight import OvernightRunner

runner = OvernightRunner(mode_override=mode)
result = runner.run()

logger.info("Result: %s", result)
sys.exit(0 if result.get("status") in ("completed", "stopped") else 1)
