"""Shared FastMCP application instance."""

import sys
from pathlib import Path

# Add elara-core to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("elara")
