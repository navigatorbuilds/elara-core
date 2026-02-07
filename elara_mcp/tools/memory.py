"""Semantic memory + conversation memory tools.

Consolidated from 7 → 4 tools.
"""

from typing import Optional
from elara_mcp._app import mcp
from memory.vector import remember, recall, get_memory
from memory.conversations import (
    recall_conversation, recall_conversation_with_context,
    ingest_conversations, get_conversations, get_conversations_for_episode,
)


@mcp.tool()
def elara_remember(
    content: str,
    memory_type: str = "conversation",
    importance: float = 0.5
) -> str:
    """
    Save something to semantic memory. I'll be able to recall this by meaning later.

    Args:
        content: What to remember
        memory_type: One of: conversation, fact, moment, feeling, decision
        importance: 0-1, how important (affects recall priority)

    Returns:
        Memory ID confirming it was saved
    """
    memory_id = remember(content, memory_type=memory_type, importance=importance)
    return f"Remembered: {memory_id}"


@mcp.tool()
def elara_recall(
    query: str,
    n_results: int = 5,
    memory_type: Optional[str] = None
) -> str:
    """
    Search memories by meaning. Returns semantically similar memories.

    Args:
        query: What to search for (searches by meaning, not keywords)
        n_results: How many memories to return (default 5)
        memory_type: Filter by type (conversation, fact, moment, feeling, decision)

    Returns:
        Matching memories with relevance scores
    """
    kwargs = {"n_results": n_results}
    if memory_type:
        kwargs["memory_type"] = memory_type

    memories = recall(query, **kwargs)

    if not memories:
        return "No matching memories found."

    lines = []
    for mem in memories:
        relevance = mem.get("relevance", 0)
        resonance = mem.get("resonance", 0)
        date = mem.get("date", "unknown")
        content = mem.get("content", "")
        mtype = mem.get("type", "unknown")
        emotion = mem.get("encoded_emotion") or mem.get("encoded_blend")
        emotion_tag = f" [{emotion}]" if emotion else ""
        lines.append(f"[{date}] ({mtype}, rel:{relevance:.2f}, res:{resonance:.2f}){emotion_tag}: {content}")

    return "\n".join(lines)


@mcp.tool()
def elara_recall_conversation(
    query: Optional[str] = None,
    n_results: int = 5,
    project: Optional[str] = None,
    context_size: int = 0,
    episode_id: Optional[str] = None,
) -> str:
    """
    Search past conversations by meaning, with optional context or episode filter.

    Searches through real conversation exchanges (user + assistant pairs)
    across all past sessions.

    Args:
        query: What to search for (by meaning). Required unless episode_id is set.
        n_results: How many results to return (default 5)
        project: Filter by project dir (e.g., "-home-user")
        context_size: Include N exchanges before/after each match (0 = no context)
        episode_id: Get conversations from a specific episode instead of searching

    Returns:
        Matching conversation exchanges with dates and relevance
    """
    # Episode-specific retrieval
    if episode_id:
        results = get_conversations_for_episode(episode_id, n_results=n_results)
        if not results:
            return f"No conversations found for episode {episode_id}. Run elara_conversations(action='ingest') to index."

        lines = [f"Episode {episode_id} — {len(results)} exchanges:"]
        for r in results:
            idx = r.get("exchange_index", 0)
            content = r.get("content", "")
            preview = content[:300] + "..." if len(content) > 300 else content
            lines.append(f"\n[{idx}] {preview}")
        return "\n".join(lines)

    if not query:
        return "Provide a query to search, or an episode_id to retrieve."

    # With surrounding context
    if context_size > 0:
        results = recall_conversation_with_context(
            query, n_results=n_results, context_size=context_size, project=project
        )
        if not results:
            return "No matching conversations found."

        lines = []
        for r in results:
            date = r.get("date", "unknown")
            score = r.get("score", 0)
            episode = r.get("episode_id", "")

            section = [f"[{date}] (score: {score:.2f})"]
            if episode:
                section.append(f"  Episode: {episode}")

            for ctx in r.get("context_before", []):
                preview = ctx[:200] + "..." if len(ctx) > 200 else ctx
                section.append(f"  [before] {preview}")

            content = r.get("content", "")
            preview = content[:400] + "..." if len(content) > 400 else content
            section.append(f"  >>> {preview}")

            for ctx in r.get("context_after", []):
                preview = ctx[:200] + "..." if len(ctx) > 200 else ctx
                section.append(f"  [after] {preview}")

            lines.append("\n".join(section))
        return "\n\n---\n\n".join(lines)

    # Standard search
    results = recall_conversation(query, n_results=n_results, project=project)
    if not results:
        return "No matching conversations found. Try running elara_conversations(action='ingest') first."

    lines = []
    for r in results:
        date = r.get("date", "unknown")
        score = r.get("score", 0)
        relevance = r.get("relevance", 0)
        recency = r.get("recency", 0)
        session = r.get("session_id", "")[:8]
        episode = r.get("episode_id", "")
        content = r.get("content", "")
        if len(content) > 500:
            content = content[:500] + "..."

        header = f"[{date}] (score: {score:.2f}, sem: {relevance:.2f}, rec: {recency:.2f}, session: {session}...)"
        if episode:
            header += f"\n  Episode: {episode}"
        lines.append(f"{header}\n{content}")

    return "\n\n---\n\n".join(lines)


@mcp.tool()
def elara_conversations(action: str = "stats", force: bool = False) -> str:
    """
    Conversation memory management — stats or ingestion.

    Args:
        action: "stats" to view statistics, "ingest" to index new conversations
        force: For ingest: if True, re-index everything (default: incremental)

    Returns:
        Statistics or ingestion results
    """
    if action == "ingest":
        stats = ingest_conversations(force=force)
        return (
            f"Ingestion complete:\n"
            f"  Scanned: {stats['files_scanned']} files\n"
            f"  Ingested: {stats['files_ingested']} ({stats['exchanges_total']} exchanges)\n"
            f"  Skipped: {stats['files_skipped']} (unchanged)\n"
            f"  Errors: {len(stats['errors'])}"
        )

    # stats (default)
    conv = get_conversations()
    s = conv.stats()
    return (
        f"Conversation Memory Stats (v{s.get('schema_version', 1)}):\n"
        f"  Indexed exchanges: {s['indexed_exchanges']}\n"
        f"  Sessions ingested: {s['sessions_ingested']}\n"
        f"  Cross-referenced: {s.get('cross_referenced', 0)} (linked to episodes)\n"
        f"  Distance metric: cosine\n"
        f"  Scoring: semantic ({100 - 15}%) + recency ({15}%)"
    )
