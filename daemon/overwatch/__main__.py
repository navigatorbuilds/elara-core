"""Allow running as: python3 -m daemon.overwatch"""
import logging
from daemon.overwatch import main

logger = logging.getLogger("elara.overwatch.__main__")

main()
