#!/usr/bin/env python3
"""
Elara MCP Server

Tools are organized into domain modules under elara_mcp/tools/.
Importing each module registers its tools with the shared mcp instance.

Modules:
- memory:    semantic memory + conversation search (7 tools)
- mood:      emotions, imprints, mode presets, status (10 tools)
- episodes:  episode lifecycle, milestones, decisions, context (13 tools)
- goals:     goals + corrections (7 tools)
- awareness: reflect, pulse, blind spots, observe, temperament (7 tools)
- dreams:    weekly, monthly, emotional pattern discovery (3 tools)
"""

from elara_mcp._app import mcp

# Import tool modules — each registers its @mcp.tool() functions on import
import elara_mcp.tools.memory
import elara_mcp.tools.mood
import elara_mcp.tools.episodes
import elara_mcp.tools.goals
import elara_mcp.tools.awareness
import elara_mcp.tools.dreams


if __name__ == "__main__":
    mcp.run()
