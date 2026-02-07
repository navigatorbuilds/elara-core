"""Maintenance tools: rebuild indexes, briefing management, snapshot.

3 tools for infrastructure management.
"""

from typing import Optional
from elara_mcp._app import mcp


@mcp.tool()
def elara_rebuild_indexes(
    collection: Optional[str] = None,
) -> str:
    """
    Rebuild ChromaDB indexes from source files.

    Rebuilds all collections from their JSON/JSONL sources.
    Use after data corruption or to re-sync after manual edits.

    Args:
        collection: Specific collection to rebuild (default: all).
            Options: memories, milestones, conversations, corrections,
                     reasoning, synthesis, briefing

    Returns:
        Rebuild results per collection
    """
    results = []

    collections_to_rebuild = (
        [collection] if collection
        else ["memories", "milestones", "conversations", "corrections",
              "reasoning", "synthesis", "briefing"]
    )

    for coll_name in collections_to_rebuild:
        try:
            result = _rebuild_collection(coll_name)
            results.append(f"  {coll_name}: {result}")
        except Exception as e:
            results.append(f"  {coll_name}: ERROR — {str(e)[:80]}")

    header = f"Rebuilt {len(collections_to_rebuild)} collection(s):"
    return header + "\n" + "\n".join(results)


def _rebuild_collection(name: str) -> str:
    """Rebuild a single ChromaDB collection."""

    if name == "memories":
        from memory.vector import VectorMemory
        vm = VectorMemory()
        count = vm.collection.count() if vm.collection else 0
        return f"OK ({count} items — memories are primary in ChromaDB, no rebuild needed)"

    if name == "milestones":
        # Milestones are indexed inline during episode operations.
        # No standalone reindex — just report count.
        try:
            from memory.episodic import EpisodicMemory
            em = EpisodicMemory()
            count = em.milestones_collection.count() if em.milestones_collection else 0
            return f"OK ({count} milestones in index — milestones are indexed inline)"
        except Exception as e:
            return f"Skipped: {e}"

    if name == "conversations":
        from memory.conversations import get_conversations
        conv = get_conversations()
        stats = conv.ingest_all(force=True)
        return f"OK ({stats.get('exchanges_total', 0)} exchanges re-indexed)"

    if name == "corrections":
        from daemon.corrections import ensure_index
        ensure_index()
        return "OK (corrections re-indexed from JSON)"

    if name == "reasoning":
        from daemon.reasoning import reindex_all as reasoning_reindex
        stats = reasoning_reindex()
        return f"OK ({stats.get('indexed', 0)} trails re-indexed)"

    if name == "synthesis":
        from daemon.synthesis import reindex_all_seeds
        stats = reindex_all_seeds()
        return f"OK ({stats.get('indexed', 0)} seeds re-indexed)"

    if name == "briefing":
        from daemon.briefing import reindex_all as briefing_reindex
        stats = briefing_reindex()
        return f"OK ({stats.get('items_in_index', 0)} items in index)"

    return f"Unknown collection: {name}"


@mcp.tool()
def elara_briefing(
    action: str = "today",
    query: Optional[str] = None,
    n: int = 5,
    feed_name: Optional[str] = None,
    url: Optional[str] = None,
    category: Optional[str] = None,
    keywords: Optional[str] = None,
) -> str:
    """
    External briefing — RSS feeds, competitor monitoring, news.

    Args:
        action: What to do:
            "today"  — Today's briefing highlights (for boot)
            "search" — Semantic search through all items
            "feeds"  — List configured feeds
            "add"    — Add a new feed (needs feed_name, url)
            "remove" — Remove a feed (needs feed_name)
            "fetch"  — Manual fetch all feeds now
            "stats"  — Feed health and item counts
        query: Search query (for search action)
        n: Number of results (default 5)
        feed_name: Feed name (for add/remove)
        url: Feed URL (for add)
        category: Feed category filter or assignment
        keywords: Comma-separated keywords for feed filtering (for add)

    Returns:
        Briefing items, feed list, or stats
    """
    from daemon.briefing import (
        get_briefing, search_briefing, list_feeds,
        add_feed, remove_feed, fetch_all, get_stats,
    )

    if action == "today":
        items = get_briefing(n=n, category=category)
        if not items:
            return "No briefing items. Add feeds with action='add' first."
        lines = [f"Today's briefing ({len(items)} items):"]
        for item in items:
            title = item.get("title", "")[:60]
            feed = item.get("feed", "")
            cat = item.get("category", "")
            lines.append(f"  [{cat}] {title} ({feed})")
            if item.get("url"):
                lines.append(f"    {item['url']}")
        return "\n".join(lines)

    if action == "search":
        if not query:
            return "Error: query is required for search."
        items = search_briefing(query, n=n, category=category)
        if not items:
            return "No matching items."
        lines = [f"Found {len(items)} items:"]
        for item in items:
            score = item.get("score", 0)
            lines.append(f"  [{score:.2f}] {item.get('title', '')[:60]}")
            if item.get("url"):
                lines.append(f"    {item['url']}")
        return "\n".join(lines)

    if action == "feeds":
        feeds = list_feeds()
        if not feeds:
            return "No feeds configured. Use action='add' to add one."
        lines = [f"{len(feeds)} feed(s):"]
        for f in feeds:
            err = f" (errors: {f['error_count']})" if f.get("error_count") else ""
            last = f.get("last_fetched", "never")
            lines.append(f"  {f['name']} [{f.get('category', 'general')}]{err}")
            lines.append(f"    URL: {f['url']}")
            lines.append(f"    Last fetched: {last}")
            if f.get("keywords"):
                lines.append(f"    Keywords: {', '.join(f['keywords'])}")
        return "\n".join(lines)

    if action == "add":
        if not feed_name or not url:
            return "Error: feed_name and url are required."
        kw_list = [k.strip() for k in keywords.split(",")] if keywords else None
        result = add_feed(feed_name, url, category=category or "general", keywords=kw_list)
        return f"Feed '{feed_name}' added ({result.get('category', 'general')})"

    if action == "remove":
        if not feed_name:
            return "Error: feed_name is required."
        removed = remove_feed(feed_name)
        return f"Feed '{feed_name}' removed." if removed else f"Feed '{feed_name}' not found."

    if action == "fetch":
        results = fetch_all()
        total = results.get("total_new", 0)
        lines = [f"Fetched all feeds ({total} new items):"]
        for name, stats in results.get("feeds", {}).items():
            err = stats.get("error")
            if err:
                lines.append(f"  {name}: ERROR — {err}")
            else:
                lines.append(f"  {name}: {stats['items_found']} found, {stats['items_new']} new")
        return "\n".join(lines)

    if action == "stats":
        stats = get_stats()
        lines = [
            f"Feeds configured: {stats['feeds_configured']}",
            f"Total items: {stats['total_items']}",
        ]
        for f in stats.get("feeds", []):
            err_str = f" (errors: {f['error_count']})" if f.get("error_count") else ""
            lines.append(f"  {f['name']} [{f['category']}]{err_str}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: today, search, feeds, add, remove, fetch, stats"


@mcp.tool()
def elara_snapshot() -> str:
    """
    Full status check: mood, presence, goals, business, memory counts.

    Returns:
        Complete state-of-the-world snapshot
    """
    from daemon.snapshot import get_snapshot

    snap = get_snapshot()
    lines = [f"Snapshot ({snap['timestamp'][:19]}):"]

    # Mood
    mood = snap.get("mood", {})
    if "error" not in mood:
        lines.append(f"  Mood: v={mood.get('valence', '?'):.2f} e={mood.get('energy', '?'):.2f} o={mood.get('openness', '?'):.2f}")
        if mood.get("description"):
            lines.append(f"    {mood['description']}")
        if mood.get("mode"):
            lines.append(f"    Mode: {mood['mode']}")

    # Episode
    ep = snap.get("episode")
    if ep:
        lines.append(f"  Episode: {ep['type']} | {ep['milestone_count']} milestones, {ep['decision_count']} decisions")

    # Goals
    goals = snap.get("goals", {})
    if "error" not in goals:
        lines.append(f"  Goals: {goals.get('active', 0)} active, {goals.get('stalled', 0)} stalled, {goals.get('done', 0)} done")

    # Business
    biz = snap.get("business", {})
    if "error" not in biz and biz.get("total", 0) > 0:
        lines.append(f"  Business: {biz.get('total', 0)} ideas ({', '.join(f'{k}: {v}' for k, v in biz.get('by_status', {}).items())})")

    # Memory
    mem = snap.get("memories", {})
    conv = snap.get("conversations", {})
    if "error" not in mem:
        lines.append(f"  Memories: {mem.get('count', 0)} semantic, {conv.get('count', 0)} conversations")

    # Corrections
    corr = snap.get("corrections", {})
    if "error" not in corr:
        lines.append(f"  Corrections: {corr.get('total', 0)}")

    # Synthesis
    synth = snap.get("synthesis", {})
    if "error" not in synth and synth.get("total", 0) > 0:
        lines.append(f"  Synthesis: {synth.get('total', 0)} ideas ({synth.get('by_status', {})})")

    # Briefing
    brief = snap.get("briefing", {})
    if "error" not in brief and brief.get("feeds_configured", 0) > 0:
        lines.append(f"  Briefing: {brief.get('feeds_configured', 0)} feeds, {brief.get('total_items', 0)} items")

    return "\n".join(lines)
