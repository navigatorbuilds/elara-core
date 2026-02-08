# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Conversation Memory v2 — Search past conversations by meaning.

Package re-exports. Composes ConversationMemory from mixins:
- ConversationBase (core.py) — DB init, manifest, text utils, stats
- IngesterMixin (ingester.py) — extract and index session files
- SearcherMixin (searcher.py) — cosine recall with recency weighting
- CrossRefMixin (crossref.py) — episode cross-referencing
"""

from typing import List, Optional, Dict, Any

from memory.conversations.core import ConversationBase
from memory.conversations.ingester import IngesterMixin
from memory.conversations.searcher import SearcherMixin
from memory.conversations.crossref import CrossRefMixin


class ConversationMemory(ConversationBase, IngesterMixin, SearcherMixin, CrossRefMixin):
    """
    Semantic search over past conversations with cosine similarity,
    recency weighting, context windows, and episode cross-referencing.
    """
    pass


# Singleton
_conversations = None


def get_conversations() -> ConversationMemory:
    global _conversations
    if _conversations is None:
        _conversations = ConversationMemory()
    return _conversations


def recall_conversation(query: str, n_results: int = 5, project: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_conversations().recall(query, n_results=n_results, project=project)


def recall_conversation_with_context(
    query: str, n_results: int = 3, context_size: int = 2, project: Optional[str] = None
) -> List[Dict[str, Any]]:
    return get_conversations().recall_with_context(
        query, n_results=n_results, context_size=context_size, project=project
    )


def ingest_conversations(force: bool = False) -> Dict[str, Any]:
    return get_conversations().ingest_all(force=force)


def get_conversations_for_episode(episode_id: str, n_results: int = 20) -> List[Dict[str, Any]]:
    return get_conversations().get_conversations_for_episode(episode_id, n_results=n_results)
