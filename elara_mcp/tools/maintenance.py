# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Maintenance tools: rebuild indexes, briefing management, snapshot, memory consolidation.

4 tools for infrastructure management.
"""

from typing import Optional
from elara_mcp._app import tool


@tool()
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
              "reasoning", "synthesis", "briefing",
              "models", "predictions", "principles"]
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

    if name == "models":
        from daemon.models import reindex_all as models_reindex
        stats = models_reindex()
        return f"OK ({stats.get('indexed', 0)} models re-indexed)"

    if name == "predictions":
        from daemon.predictions import reindex_all as predictions_reindex
        stats = predictions_reindex()
        return f"OK ({stats.get('indexed', 0)} predictions re-indexed)"

    if name == "principles":
        from daemon.principles import reindex_all as principles_reindex
        stats = principles_reindex()
        return f"OK ({stats.get('indexed', 0)} principles re-indexed)"

    return f"Unknown collection: {name}"


@tool()
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


@tool()
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


@tool()
def elara_memory_consolidation(
    action: str = "stats",
    resolve_ids: Optional[str] = None,
) -> str:
    """
    Memory consolidation — merge duplicates, decay unused, archive weak,
    detect contradictions.

    Biological-like memory maintenance. Runs automatically during overnight
    brain, or trigger manually here.

    Args:
        action: What to do:
            "stats"          — Consolidation history, memory count, contradiction count
            "consolidate"    — Run full consolidation pass (merge/decay/archive/contradictions)
            "duplicates"     — Show potential duplicate pairs with similarity scores
            "at_risk"        — Show memories with importance < 0.2
            "contradictions" — Show detected memory contradictions
            "resolve"        — Resolve a contradiction (needs resolve_ids "id_a,id_b,keep")
            "sweep"          — Show junk memories that would be cleaned (dry run)
            "sweep_confirm"  — Archive and delete junk memories
        resolve_ids: For resolve action: "id_a,id_b,newer" or "id_a,id_b,a" or "id_a,id_b,b"

    Returns:
        Consolidation results or statistics
    """
    from memory.consolidation import get_consolidator

    c = get_consolidator()

    if action == "stats":
        s = c.stats()
        lines = [
            f"Memory count: {s['memory_count']}",
            f"Recall log entries: {s['recall_log_entries']}",
            f"Archived memories: {s['archive_size']}",
            f"At-risk (< 0.2): {s['at_risk_count']}",
            f"Contradictions: {s.get('contradictions_count', 0)}",
            f"Total consolidation runs: {s['total_runs']}",
            f"Last run: {s.get('last_run', 'never')}",
        ]
        lr = s.get("last_result")
        if lr:
            lines.append(f"Last result: merged={lr.get('merged', 0)}, "
                          f"archived={lr.get('archived', 0)}, "
                          f"strengthened={lr.get('strengthened', 0)}, "
                          f"decayed={lr.get('decayed', 0)}, "
                          f"contradictions={lr.get('contradictions_found', 0)}")
        return "\n".join(lines)

    if action == "consolidate":
        result = c.consolidate()
        lines = [
            "Consolidation complete:",
            f"  Strengthened: {result.get('strengthened', 0)}",
            f"  Decayed: {result.get('decayed', 0)}",
            f"  Duplicate pairs found: {result.get('duplicate_pairs_found', 0)}",
            f"  Merged: {result.get('merged', 0)}",
            f"  Archived: {result.get('archived', 0)}",
            f"  Contradictions found: {result.get('contradictions_found', 0)}",
            f"  Memories remaining: {result.get('memories_after', '?')}",
        ]
        return "\n".join(lines)

    if action == "duplicates":
        dupes = c.find_duplicates()
        if not dupes:
            return "No duplicate pairs found above 0.85 similarity."
        lines = [f"Found {len(dupes)} duplicate pair(s):"]
        for id_a, id_b, sim in dupes[:20]:
            lines.append(f"  {id_a[:8]}..{id_b[:8]} — similarity: {sim:.4f}")
        return "\n".join(lines)

    if action == "at_risk":
        at_risk = c.get_at_risk()
        if not at_risk:
            return "No memories at risk (all importance >= 0.2)."
        lines = [f"{len(at_risk)} memories at risk:"]
        for mem in at_risk[:20]:
            lines.append(f"  [{mem['importance']:.3f}] {mem['type']}: {mem['content']}")
            lines.append(f"    ID: {mem['memory_id']}  Date: {mem['date']}")
        return "\n".join(lines)

    if action == "contradictions":
        contras = c.get_contradictions()
        if not contras:
            return "No contradictions detected."
        lines = [f"{len(contras)} contradiction(s) found:"]
        for i, con in enumerate(contras[:15]):
            lines.append(f"\n  [{i+1}] similarity: {con['similarity']:.4f}")
            lines.append(f"    A ({con['date_a']}): {con['content_a'][:100]}")
            lines.append(f"    B ({con['date_b']}): {con['content_b'][:100]}")
            lines.append(f"    IDs: {con['id_a'][:12]}.. vs {con['id_b'][:12]}..")
        return "\n".join(lines)

    if action == "resolve":
        if not resolve_ids:
            return "Error: resolve_ids required. Format: 'id_a,id_b,newer' or 'id_a,id_b,a' or 'id_a,id_b,b'"
        parts = [p.strip() for p in resolve_ids.split(",")]
        if len(parts) != 3:
            return "Error: resolve_ids must be 'id_a,id_b,keep' where keep is 'newer', 'a', or 'b'"
        id_a, id_b, keep = parts
        kept = c.resolve_contradiction(id_a, id_b, keep=keep)
        if kept:
            return f"Resolved: kept {kept[:12]}.. , archived the other."
        return "Resolution failed — memories not found or invalid keep value."

    if action == "sweep":
        result = c.sweep_junk(dry_run=True)
        junk = result["junk"]
        if not junk:
            return "No junk memories found."
        lines = [f"Found {len(junk)} junk memories (dry run — use sweep_confirm to archive):"]
        for item in junk:
            lines.append(f"  [{item['importance']:.2f}] {item['reason']}: {item['content'][:80]}")
        return "\n".join(lines)

    if action == "sweep_confirm":
        result = c.sweep_junk(dry_run=False)
        return (f"Swept {result.get('archived', 0)} junk memories "
                f"(archived before deletion). {c.vm.collection.count()} remaining.")

    return f"Unknown action: {action}. Use: stats, consolidate, duplicates, at_risk, contradictions, resolve, sweep, sweep_confirm"
