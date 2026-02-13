# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Overnight research — web search + URL fetch for autonomous thinking.

Uses DuckDuckGo (no API key needed). Falls back gracefully if unavailable.
"""

import logging
import re
from typing import List, Dict, Optional
from html.parser import HTMLParser

logger = logging.getLogger("elara.overnight")

# Pattern to detect research requests in model output
RESEARCH_PATTERN = re.compile(r"^RESEARCH:\s*(.+)$", re.MULTILINE)


class _TextExtractor(HTMLParser):
    """Minimal HTML-to-text extractor."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._text.append(text)

    def get_text(self) -> str:
        return " ".join(self._text)


def web_search(query: str, n_results: int = 3) -> List[Dict[str, str]]:
    """
    Search the web via DuckDuckGo. Returns list of {title, url, snippet}.

    Falls back to empty list if library is missing or search fails.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("ddgs/duckduckgo-search not installed, skipping research")
            return []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=n_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        logger.warning("Web search failed for '%s': %s", query, e)
        return []


def fetch_url(url: str, max_chars: int = 4000) -> Optional[str]:
    """
    Fetch a URL and extract plain text. Returns None on failure.
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Elara-Overnight/1.0 (research bot)",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        extractor = _TextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        return text[:max_chars] if text else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        logger.debug("Fetch failed for %s: %s", url, e)
        return None
    except Exception as e:
        logger.debug("Fetch unexpected error for %s: %s", url, e)
        return None


def research_if_needed(round_output: str, enable: bool = True) -> str:
    """
    Parse model output for RESEARCH: markers, run searches, return enriched context.

    Returns formatted research results string (empty if none needed).
    """
    if not enable:
        return ""

    matches = RESEARCH_PATTERN.findall(round_output)
    if not matches:
        return ""

    all_results = []
    queries_run = 0

    for query in matches[:3]:  # Cap at 3 research queries per round
        query = query.strip()
        if not query:
            continue

        logger.info("  Research: %s", query)
        results = web_search(query, n_results=3)
        queries_run += 1

        if results:
            lines = [f"Search: {query}"]
            for r in results:
                lines.append(f"  [{r['title']}]({r['url']})")
                if r["snippet"]:
                    lines.append(f"  {r['snippet'][:200]}")
            all_results.append("\n".join(lines))

    if not all_results:
        return ""

    return "=== RESEARCH RESULTS ===\n" + "\n\n".join(all_results) + "\n"
