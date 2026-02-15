#!/usr/bin/env python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara MCP Server

Tools are organized into domain modules under elara_mcp/tools/.
Importing each module registers its tools via the profile-aware @tool() decorator.

Profiles:
  --profile full  → 39 individual tool schemas (backward compatible)
  --profile lean  → 7 core schemas + 1 elara_do meta-tool (default, ~5% context)

39 tools across 12 modules:
- memory:       elara_remember, elara_recall, elara_recall_conversation, elara_conversations (4)
- mood:         elara_mood, elara_mood_adjust, elara_imprint, elara_mode, elara_status (5)
- episodes:     elara_episode_start, elara_episode_note, elara_episode_end, elara_episode_query, elara_context (5)
- goals:        elara_goal, elara_goal_boot, elara_correction, elara_correction_boot, elara_handoff (5)
- awareness:    elara_reflect, elara_insight, elara_intention, elara_observe, elara_temperament (5)
- dreams:       elara_dream, elara_dream_info (2)
- cognitive:    elara_reasoning, elara_outcome, elara_synthesis (3)
- cognition_3d: elara_model, elara_prediction, elara_principle (3)
- business:     elara_business (1)
- llm:          elara_llm (1)
- gmail:        elara_gmail (1)
- maintenance:  elara_rebuild_indexes, elara_briefing, elara_snapshot, elara_memory_consolidation (4)
"""

from elara_mcp._app import mcp, get_profile

# Import tool modules — each registers its tools via @tool() on import
import elara_mcp.tools.memory
import elara_mcp.tools.mood
import elara_mcp.tools.episodes
import elara_mcp.tools.goals
import elara_mcp.tools.awareness
import elara_mcp.tools.dreams
import elara_mcp.tools.cognitive
import elara_mcp.tools.cognition_3d
import elara_mcp.tools.business
import elara_mcp.tools.llm
import elara_mcp.tools.gmail
import elara_mcp.tools.maintenance

# In lean mode, register the elara_do meta-tool for dispatching
if get_profile() == "lean":
    import elara_mcp.tools.meta


if __name__ == "__main__":
    mcp.run()
