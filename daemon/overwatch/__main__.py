# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Allow running as: python3 -m daemon.overwatch"""
import logging
from daemon.overwatch import main

logger = logging.getLogger("elara.overwatch.__main__")

main()
