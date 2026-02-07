"""
Elara Briefing Engine — Ingest external signals and surface relevant items.

RSS/Atom feed monitoring with keyword filtering, semantic search,
and boot-time briefing generation. Ingestion runs standalone (cron),
Claude tokens only spent when querying during sessions.

Storage:
- Config: ~/.claude/elara-feeds.json (feed definitions)
- Items:  ~/.claude/elara-briefing-db/ (ChromaDB collection, cosine)
- Brief:  ~/.claude/elara-briefing.json (pre-computed for boot)
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.paths import get_paths
from daemon.schemas import atomic_write_json

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

logger = logging.getLogger("elara.briefing")

# Paths
_p = get_paths()
FEEDS_CONFIG = _p.feeds_config
BRIEFING_DB_DIR = _p.briefing_db
BRIEFING_FILE = _p.briefing_file

# Defaults
MAX_ITEMS_PER_FEED = 20
MAX_ITEM_AGE_DAYS = 30
DEFAULT_RELEVANCE_THRESHOLD = 0.3


# ============================================================================
# Feed config management
# ============================================================================

def _load_feeds() -> List[Dict]:
    if not FEEDS_CONFIG.exists():
        return []
    try:
        with open(FEEDS_CONFIG, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_feeds(feeds: List[Dict]):
    atomic_write_json(FEEDS_CONFIG, feeds)


def add_feed(
    name: str,
    url: str,
    category: str = "general",
    keywords: Optional[List[str]] = None,
) -> Dict:
    """Add or update a feed configuration."""
    feeds = _load_feeds()

    # Update existing or append new
    existing = next((f for f in feeds if f["name"] == name), None)
    feed_data = {
        "name": name,
        "url": url,
        "category": category,
        "keywords": keywords or [],
        "added": datetime.now().isoformat(),
        "last_fetched": None,
        "error_count": 0,
        "last_error": None,
    }

    if existing:
        existing.update(feed_data)
    else:
        feeds.append(feed_data)

    _save_feeds(feeds)
    return feed_data


def remove_feed(name: str) -> bool:
    """Remove a feed by name. Returns True if found and removed."""
    feeds = _load_feeds()
    original_len = len(feeds)
    feeds = [f for f in feeds if f["name"] != name]
    if len(feeds) < original_len:
        _save_feeds(feeds)
        return True
    return False


def list_feeds() -> List[Dict]:
    """List all configured feeds with stats."""
    return _load_feeds()


# ============================================================================
# ChromaDB collection
# ============================================================================

_chroma_client = None
_collection = None


def _get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    if not CHROMA_AVAILABLE:
        return None

    BRIEFING_DB_DIR.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(BRIEFING_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    _collection = _chroma_client.get_or_create_collection(
        name="elara_briefing",
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


# ============================================================================
# Item management
# ============================================================================

def _item_id(feed_name: str, title: str, url: str) -> str:
    """Generate stable item ID from content."""
    raw = f"{feed_name}:{title}:{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _keyword_score(text: str, keywords: List[str]) -> float:
    """Score text against keyword list. 0-1 range."""
    if not keywords:
        return 0.5  # No filter = neutral
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(1.0, matches / max(1, len(keywords)))


def ingest_item(
    feed_name: str,
    category: str,
    title: str,
    summary: str,
    url: str,
    published: str,
    keywords: Optional[List[str]] = None,
) -> bool:
    """
    Ingest a single feed item into ChromaDB.
    Returns True if new item, False if duplicate.
    """
    collection = _get_collection()
    if collection is None:
        return False

    item_id = _item_id(feed_name, title, url)

    # Check duplicate
    try:
        existing = collection.get(ids=[item_id])
        if existing and existing["ids"]:
            return False
    except Exception:
        pass

    # Score against keywords
    text = f"{title} {summary}"
    kw_score = _keyword_score(text, keywords or [])

    now = datetime.now().isoformat()
    collection.add(
        ids=[item_id],
        documents=[text],
        metadatas=[{
            "feed_name": feed_name,
            "category": category,
            "title": title,
            "url": url,
            "published": published or now,
            "fetched": now,
            "keyword_score": kw_score,
        }],
    )
    return True


def fetch_feed(feed_config: Dict) -> Dict[str, Any]:
    """
    Fetch and ingest items from a single feed.
    Returns stats: {items_found, items_new, error}.
    """
    try:
        import feedparser
    except ImportError:
        return {"items_found": 0, "items_new": 0, "error": "feedparser not installed"}

    url = feed_config["url"]
    name = feed_config["name"]
    category = feed_config.get("category", "general")
    keywords = feed_config.get("keywords", [])

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            error_msg = str(feed.bozo_exception)[:100]
            return {"items_found": 0, "items_new": 0, "error": error_msg}

        items_new = 0
        entries = feed.entries[:MAX_ITEMS_PER_FEED]
        for entry in entries:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))[:500]
            link = entry.get("link", "")
            published = entry.get("published", "")

            if title:
                was_new = ingest_item(
                    feed_name=name,
                    category=category,
                    title=title,
                    summary=summary,
                    url=link,
                    published=published,
                    keywords=keywords,
                )
                if was_new:
                    items_new += 1

        return {"items_found": len(entries), "items_new": items_new, "error": None}

    except Exception as e:
        return {"items_found": 0, "items_new": 0, "error": str(e)[:100]}


def fetch_all() -> Dict[str, Any]:
    """Fetch all configured feeds. Returns per-feed stats."""
    feeds = _load_feeds()
    results = {}
    total_new = 0

    for feed in feeds:
        stats = fetch_feed(feed)
        results[feed["name"]] = stats
        total_new += stats["items_new"]

        # Update feed config with fetch stats
        feed["last_fetched"] = datetime.now().isoformat()
        if stats["error"]:
            feed["error_count"] = feed.get("error_count", 0) + 1
            feed["last_error"] = stats["error"]
        else:
            feed["error_count"] = 0
            feed["last_error"] = None

    _save_feeds(feeds)

    return {"feeds": results, "total_new": total_new}


# ============================================================================
# Search and retrieval
# ============================================================================

def search_briefing(query: str, n: int = 5, category: str = None) -> List[Dict]:
    """Semantic search through briefing items."""
    collection = _get_collection()
    if collection is None:
        return []

    where = {"category": category} if category else None

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n, 20),
            where=where,
        )
    except Exception as e:
        logger.warning(f"Briefing search failed: {e}")
        return []

    items = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            score = 1.0 - dist  # cosine distance to similarity

            items.append({
                "id": doc_id,
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "feed": meta.get("feed_name", ""),
                "category": meta.get("category", ""),
                "published": meta.get("published", ""),
                "score": round(score, 3),
            })

    return items


def get_briefing(n: int = 5, category: str = None) -> List[Dict]:
    """Get today's pre-computed briefing or generate fresh."""
    # Try pre-computed first
    if BRIEFING_FILE.exists():
        try:
            data = json.loads(BRIEFING_FILE.read_text())
            generated = data.get("generated", "")
            # Use if less than 24h old
            if generated:
                gen_time = datetime.fromisoformat(generated)
                if datetime.now() - gen_time < timedelta(hours=24):
                    items = data.get("items", [])
                    if category:
                        items = [i for i in items if i.get("category") == category]
                    return items[:n]
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    # Fallback: search for recent items
    return search_briefing("recent news updates", n=n, category=category)


def generate_daily_briefing(n: int = 10) -> Dict:
    """
    Generate and save daily briefing.
    Called by cron script, not during sessions.
    """
    collection = _get_collection()
    if collection is None:
        return {"items": [], "generated": datetime.now().isoformat()}

    # Get recent items (last 48h)
    cutoff = (datetime.now() - timedelta(hours=48)).isoformat()

    try:
        # Get all recent items
        results = collection.get(
            where={"fetched": {"$gte": cutoff}},
            limit=50,
        )
    except Exception:
        # Fallback: get most recent by query
        results = collection.query(
            query_texts=["latest news updates developments"],
            n_results=n * 2,
        )
        if results and results["ids"]:
            results = {
                "ids": results["ids"][0],
                "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            }
        else:
            results = {"ids": [], "metadatas": []}

    items = []
    for i, doc_id in enumerate(results.get("ids", [])):
        meta = results["metadatas"][i] if i < len(results.get("metadatas", [])) else {}
        kw_score = float(meta.get("keyword_score", 0.5))

        items.append({
            "id": doc_id,
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
            "feed": meta.get("feed_name", ""),
            "category": meta.get("category", ""),
            "published": meta.get("published", ""),
            "keyword_score": kw_score,
        })

    # Sort by keyword relevance
    items.sort(key=lambda x: x.get("keyword_score", 0), reverse=True)
    items = items[:n]

    briefing = {
        "generated": datetime.now().isoformat(),
        "items": items,
    }

    atomic_write_json(BRIEFING_FILE, briefing)

    return briefing


# ============================================================================
# Stats and boot integration
# ============================================================================

def get_stats() -> Dict[str, Any]:
    """Feed health stats."""
    feeds = _load_feeds()
    collection = _get_collection()
    total_items = collection.count() if collection else 0

    return {
        "feeds_configured": len(feeds),
        "total_items": total_items,
        "feeds": [
            {
                "name": f["name"],
                "category": f.get("category", "general"),
                "last_fetched": f.get("last_fetched"),
                "error_count": f.get("error_count", 0),
                "last_error": f.get("last_error"),
            }
            for f in feeds
        ],
    }


def boot_summary() -> str:
    """Format briefing for boot output. Max 5 lines."""
    items = get_briefing(n=5)
    if not items:
        return ""

    lines = []
    for item in items[:5]:
        title = item.get("title", "")[:60]
        feed = item.get("feed", "")
        if title:
            suffix = f" ({feed})" if feed else ""
            lines.append(f"[Briefing] {title}{suffix}")

    return "\n".join(lines)


def reindex_all() -> Dict[str, Any]:
    """
    Rebuild the briefing ChromaDB collection.
    Since items are already in ChromaDB, this resets and re-adds nothing
    (items come from RSS, not local JSON). Returns stats.
    """
    collection = _get_collection()
    if collection is None:
        return {"status": "chromadb_unavailable"}

    count = collection.count()
    return {
        "status": "ok",
        "items_in_index": count,
        "note": "Briefing items come from RSS feeds. Run fetch_all() to re-ingest.",
    }
