"""
Elara Conversation Memory — CLI interface.

Usage: python -m memory.conversations [ingest|search|context|stats|test|episode]
"""

import sys
import glob as glob_mod
from pathlib import Path

from memory.conversations.core import PROJECTS_DIR


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m memory.conversations [ingest|search|context|stats|test|episode]")
        print("  ingest [--force]       — Index all session files")
        print("  search <query>         — Search past conversations")
        print("  context <query>        — Search with surrounding context")
        print("  episode <episode_id>   — Get conversations for an episode")
        print("  stats                  — Show index statistics")
        print("  test                   — Test extraction on one file")
        sys.exit(1)

    # Import here to avoid circular imports at module load
    from memory.conversations import ConversationMemory

    cmd = sys.argv[1]

    if cmd == "test":
        files = sorted(glob_mod.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))
        if not files:
            print("No JSONL files found.")
            sys.exit(1)

        test_file = files[0]
        print(f"Testing extraction on: {test_file}")
        cm = ConversationMemory()
        exchanges = cm.extract_exchanges(test_file)
        print(f"Found {len(exchanges)} exchanges:")
        for ex in exchanges[:5]:
            user_preview = ex["user_text"][:80]
            assistant_preview = ex["assistant_text"][:80]
            print(f"\n  [{ex['exchange_index']}] User: {user_preview}")
            print(f"      Elara: {assistant_preview}")

    elif cmd == "ingest":
        force = "--force" in sys.argv
        print("Ingesting conversations...")
        cm = ConversationMemory()
        stats = cm.ingest_all(force=force)
        print(f"Scanned: {stats['files_scanned']} files")
        print(f"Ingested: {stats['files_ingested']} files ({stats['exchanges_total']} exchanges)")
        print(f"Skipped: {stats['files_skipped']} (unchanged)")
        if stats["errors"]:
            print(f"Errors: {len(stats['errors'])}")
            for err in stats["errors"][:5]:
                print(f"  - {err}")
        print(f"Total indexed: {cm.count()}")

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: search <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        print(f"Searching: \"{query}\"")
        cm = ConversationMemory()
        results = cm.recall(query, n_results=5)
        if not results:
            print("No results. Have you run 'ingest' first?")
        for r in results:
            ep = f" [ep:{r['episode_id'][:10]}]" if r.get("episode_id") else ""
            print(f"\n[{r['date']}] (score: {r['score']:.2f}, sem: {r['relevance']:.2f}, rec: {r['recency']:.2f}){ep}")
            print(f"  session: {r['session_id'][:8]}...")
            print(r["content"][:300])
            print("---")

    elif cmd == "context":
        if len(sys.argv) < 3:
            print("Usage: context <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        print(f"Context search: \"{query}\"")
        cm = ConversationMemory()
        results = cm.recall_with_context(query, n_results=3, context_size=2)
        for r in results:
            print(f"\n[{r['date']}] (score: {r['score']:.2f})")
            if r.get("context_before"):
                for ctx in r["context_before"]:
                    print(f"  BEFORE: {ctx[:100]}...")
            print(f"  >>> MATCH: {r['content'][:200]}...")
            if r.get("context_after"):
                for ctx in r["context_after"]:
                    print(f"  AFTER: {ctx[:100]}...")
            print("---")

    elif cmd == "episode":
        if len(sys.argv) < 3:
            print("Usage: episode <episode_id>")
            sys.exit(1)
        ep_id = sys.argv[2]
        cm = ConversationMemory()
        convos = cm.get_conversations_for_episode(ep_id)
        if not convos:
            print(f"No conversations found for episode {ep_id}")
        else:
            print(f"Found {len(convos)} exchanges for episode {ep_id}:")
            for c in convos:
                print(f"\n  [{c['exchange_index']}] {c['content'][:200]}...")

    elif cmd == "stats":
        cm = ConversationMemory()
        s = cm.stats()
        print(f"Schema version: {s['schema_version']}")
        print(f"Indexed exchanges: {s['indexed_exchanges']}")
        print(f"Sessions ingested: {s['sessions_ingested']}")
        print(f"Cross-referenced: {s['cross_referenced']} (linked to episodes)")
        print(f"Manifest entries: {s['manifest_entries']}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
