#!/usr/bin/env python3
"""
Elara Daily Briefing — Standalone cron script.

Fetches all configured RSS feeds, ingests into ChromaDB,
generates daily briefing summary for boot.

Zero Claude tokens. Runs entirely standalone.

Setup:
    crontab -e
    0 8 * * * /path/to/venv/bin/python -m scripts.elara_briefing

Manual run:
    elara briefing  # or: python -m scripts.elara_briefing
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from core.paths import get_paths

# Setup logging
LOG_FILE = get_paths().briefing_log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("elara.briefing.cron")


def main():
    """Fetch feeds, ingest items, generate daily briefing."""
    logger.info("=== Briefing cron started ===")

    try:
        from daemon.briefing import (
            list_feeds, fetch_all, generate_daily_briefing, get_stats,
        )
    except ImportError as e:
        logger.error(f"Import failed: {e}")
        logger.error("Make sure you're running from the elara-core venv")
        sys.exit(1)

    # Check feeds configured
    feeds = list_feeds()
    if not feeds:
        logger.info("No feeds configured. Use elara_business tool to add feeds.")
        logger.info("Example feeds:")
        logger.info("  - Flutter Blog: https://medium.com/feed/flutter")
        logger.info("  - Dart Blog: https://medium.com/feed/dartlang")
        logger.info("  - HN Flutter: https://hnrss.org/newest?q=flutter")
        return

    logger.info(f"Fetching {len(feeds)} feeds...")

    # Fetch all feeds
    results = fetch_all()
    total_new = results.get("total_new", 0)

    # Log per-feed results
    for name, stats in results.get("feeds", {}).items():
        found = stats.get("items_found", 0)
        new = stats.get("items_new", 0)
        error = stats.get("error")
        if error:
            logger.warning(f"  {name}: ERROR — {error}")
        else:
            logger.info(f"  {name}: {found} found, {new} new")

    logger.info(f"Total new items: {total_new}")

    # Generate daily briefing
    logger.info("Generating daily briefing...")
    briefing = generate_daily_briefing(n=10)
    items = briefing.get("items", [])
    logger.info(f"Briefing generated: {len(items)} items")

    for item in items[:5]:
        logger.info(f"  [{item.get('category', '?')}] {item.get('title', '')[:60]}")

    # Stats
    stats = get_stats()
    logger.info(f"Total items in DB: {stats.get('total_items', 0)}")
    logger.info("=== Briefing cron complete ===")


if __name__ == "__main__":
    main()
