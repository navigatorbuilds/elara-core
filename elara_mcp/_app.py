"""Shared FastMCP application instance."""

import logging
from pathlib import Path

from core.paths import get_paths

# Central logging config — all elara.* loggers route here
_log_path = get_paths().daemon_log
_log_path.parent.mkdir(parents=True, exist_ok=True)
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
