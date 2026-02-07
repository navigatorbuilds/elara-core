"""Shared FastMCP application instance."""

import logging
import sys
from pathlib import Path

# Add elara-core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Central logging config — all elara.* loggers route here
_log_path = Path.home() / ".claude" / "elara-daemon.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(_log_path)),
    ],
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("elara")
