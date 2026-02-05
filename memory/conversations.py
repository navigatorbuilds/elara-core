"""
Elara Conversation Memory v2 — Search past conversations by meaning.

Upgrades from v1:
- Cosine distance (better relevance scores, 0-1 where 1 = perfect match)
- Recency-weighted scoring (recent conversations rank higher)
- Context windows (return surrounding exchanges, not just the match)
- Cross-referencing (link conversations to episodic milestones by timestamp)
- Auto-ingestion ready (called from boot.py on every startup)
"""

import json
import os
import hashlib
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

CONVERSATIONS_DIR = Path.home() / ".claude" / "elara-conversations-db"
MANIFEST_PATH = CONVERSATIONS_DIR / "ingested.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
EPISODES_DIR = Path.home() / ".claude" / "elara-episodes"
EPISODES_INDEX = EPISODES_DIR / "index.json"

# Current schema version — bump to force re-index on upgrade
SCHEMA_VERSION = 2

# Regex to strip <system-reminder>...</system-reminder> blocks
SYSTEM_REMINDER_RE = re.compile(r'<system-reminder>.*?</system-reminder>', re.DOTALL)

# Recency scoring parameters
RECENCY_HALF_LIFE_DAYS = 30  # After 30 days, recency factor = 0.5
RECENCY_WEIGHT = 0.15  # 15% of final score comes from recency


class ConversationMemory:
    """
    Semantic search over past conversations with cosine similarity,
    recency weighting, context windows, and episode cross-referencing.
    """

    def __init__(self):
        self.client = None
        self.collection = None

        if CHROMA_AVAILABLE:
            self._init_db()

    def _init_db(self):
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(CONVERSATIONS_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        # Check if we need to migrate from v1 (L2) to v2 (cosine)
        needs_migration = self._check_migration()

        if needs_migration:
            self._migrate_to_v2()

        self.collection = self.client.get_or_create_collection(
            name="elara_conversations_v2",
            metadata={
                "description": "Elara's conversation memory — cosine similarity",
                "hnsw:space": "cosine",
            }
        )

    def _check_migration(self) -> bool:
        """Check if we need to migrate from v1 to v2."""
        manifest = self._load_manifest()

        # If manifest has our version, no migration needed
        if manifest.get("_schema_version") == SCHEMA_VERSION:
            return False

        # If v2 collection already exists and has data, just update manifest
        try:
            existing = self.client.get_collection("elara_conversations_v2")
            if existing.count() > 0:
                return False
        except Exception:
            pass

        return True

    def _migrate_to_v2(self):
        """Migrate from v1 (L2 distance) to v2 (cosine distance)."""
        # Delete old v1 collection if it exists
        try:
            self.client.delete_collection("elara_conversations")
        except Exception:
            pass

        # Delete old v2 collection if it exists but is empty/corrupt
        try:
            self.client.delete_collection("elara_conversations_v2")
        except Exception:
            pass

        # Clear manifest to force full re-ingestion
        manifest = {"_schema_version": SCHEMA_VERSION}
        self._save_manifest(manifest)

    def _load_manifest(self) -> Dict[str, Any]:
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH) as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: Dict[str, Any]):
        manifest["_schema_version"] = SCHEMA_VERSION
        with open(MANIFEST_PATH, 'w') as f:
            json.dump(manifest, f, indent=2)

    def _generate_id(self, session_id: str, exchange_index: int, timestamp: str) -> str:
        content = f"{session_id}:{exchange_index}:{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _clean_text(self, text: str) -> str:
        """Strip system-reminder blocks and clean up text."""
        text = SYSTEM_REMINDER_RE.sub('', text)
        text = text.strip()
        return text

    def _extract_user_text(self, message: dict) -> Optional[str]:
        """Extract user text from a message entry. Returns None if not real user input."""
        content = message.get("message", {}).get("content", "")

        if isinstance(content, str):
            text = self._clean_text(content)
            if text:
                return text
            return None
        elif isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned:
                        texts.append(cleaned)
            if texts:
                return "\n".join(texts)
        return None

    def _extract_assistant_text(self, message: dict) -> Optional[str]:
        """Extract assistant text from a message entry. Skip tool_use, thinking blocks."""
        content = message.get("message", {}).get("content", [])

        if isinstance(content, str):
            text = self._clean_text(content)
            return text if text else None

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    cleaned = self._clean_text(block.get("text", ""))
                    if cleaned:
                        texts.append(cleaned)
            if texts:
                return "\n".join(texts)
        return None

    # =========================================================================
    # EPISODE CROSS-REFERENCING
    # =========================================================================

    def _load_episode_ranges(self) -> List[Dict[str, Any]]:
        """
        Load episode time ranges for cross-referencing.
        Returns list of {id, started, ended} dicts.
        """
        if not EPISODES_INDEX.exists():
            return []

        try:
            index = json.loads(EPISODES_INDEX.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        ranges = []
        for episode_id in index.get("episodes", []):
            # Load episode file to get time range
            date_part = episode_id[:7]
            ep_path = EPISODES_DIR / date_part / f"{episode_id}.json"
            if not ep_path.exists():
                continue

            try:
                ep = json.loads(ep_path.read_text())
                started = ep.get("started", "")
                ended = ep.get("ended", "")
                ranges.append({
                    "id": episode_id,
                    "started": started,
                    "ended": ended,
                    "projects": ep.get("projects", []),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return ranges

    def _match_episode(self, timestamp: str, episode_ranges: List[Dict]) -> Optional[str]:
        """
        Find which episode a conversation timestamp belongs to.
        Returns episode_id or None.
        """
        if not timestamp or not episode_ranges:
            return None

        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Remove timezone for comparison since episodes use naive timestamps
            if ts.tzinfo:
                ts = ts.replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

        for ep in episode_ranges:
            try:
                started = datetime.fromisoformat(ep["started"])
                if ep["ended"]:
                    ended = datetime.fromisoformat(ep["ended"])
                else:
                    # Open episode — assume it's the current one
                    ended = datetime.now()

                if started <= ts <= ended:
                    return ep["id"]
            except (ValueError, TypeError):
                continue

        return None

    # =========================================================================
    # EXTRACTION & INGESTION
    # =========================================================================

    def extract_exchanges(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse a JSONL session file into exchange pairs.
        Each exchange = user text + next assistant text response.
        """
        exchanges = []
        entries = []

        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Filter to user and assistant messages only
        messages = []
        for entry in entries:
            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue
            if entry.get("isSidechain"):
                continue
            messages.append(entry)

        # Pair: user text + following assistant text
        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.get("type") == "user":
                user_text = self._extract_user_text(msg)
                user_ts = msg.get("timestamp", "")

                if user_text:
                    assistant_text = None
                    assistant_ts = ""
                    j = i + 1
                    while j < len(messages):
                        next_msg = messages[j]
                        if next_msg.get("type") == "assistant":
                            text = self._extract_assistant_text(next_msg)
                            if text:
                                assistant_text = text
                                assistant_ts = next_msg.get("timestamp", "")
                                break
                            j += 1
                        elif next_msg.get("type") == "user":
                            break
                        else:
                            j += 1

                    if assistant_text:
                        exchanges.append({
                            "user_text": user_text,
                            "assistant_text": assistant_text,
                            "timestamp": user_ts or assistant_ts,
                            "exchange_index": len(exchanges),
                        })

            i += 1

        return exchanges

    def ingest_file(
        self,
        file_path: str,
        manifest: Dict[str, Any],
        episode_ranges: Optional[List[Dict]] = None,
    ) -> int:
        """
        Ingest a single JSONL file into ChromaDB.
        Now with episode cross-referencing.
        """
        if not self.collection:
            return 0

        path = Path(file_path)
        session_id = path.stem
        project_dir = path.parent.name

        # Get project cwd from first user entry
        project_cwd = ""
        with open(file_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "user" and entry.get("cwd"):
                        project_cwd = entry["cwd"]
                        break
                except json.JSONDecodeError:
                    continue

        exchanges = self.extract_exchanges(file_path)
        if not exchanges:
            return 0

        # Delete old entries for this session
        try:
            existing = self.collection.get(where={"session_id": session_id})
            if existing and existing["ids"]:
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass

        # Prepare batch
        ids = []
        documents = []
        metadatas = []

        for ex in exchanges:
            doc = f"User: {ex['user_text']}\n\nElara: {ex['assistant_text']}"
            if len(doc) > 2000:
                doc = doc[:2000]

            ex_id = self._generate_id(session_id, ex["exchange_index"], ex["timestamp"])

            # Parse timestamp
            date_str = ""
            hour = -1
            epoch = 0.0
            if ex["timestamp"]:
                try:
                    dt = datetime.fromisoformat(ex["timestamp"].replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                    hour = dt.hour
                    epoch = dt.timestamp()
                except (ValueError, TypeError):
                    pass

            # Match to episode
            episode_id = ""
            if episode_ranges:
                matched = self._match_episode(ex["timestamp"], episode_ranges)
                if matched:
                    episode_id = matched

            meta = {
                "session_id": session_id,
                "project_dir": project_dir,
                "project_cwd": project_cwd,
                "timestamp": ex["timestamp"],
                "date": date_str,
                "hour": hour,
                "epoch": epoch,
                "exchange_index": ex["exchange_index"],
                "total_exchanges": len(exchanges),
                "user_text_preview": ex["user_text"][:100],
                "episode_id": episode_id,
            }

            ids.append(ex_id)
            documents.append(doc)
            metadatas.append(meta)

        # Batch add
        if documents:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)

        # Update manifest
        stat = os.stat(file_path)
        manifest[file_path] = {
            "last_modified": stat.st_mtime,
            "size_bytes": stat.st_size,
            "exchanges_ingested": len(exchanges),
            "session_id": session_id,
        }

        return len(exchanges)

    def ingest_all(self, force: bool = False) -> Dict[str, Any]:
        """
        Walk all project dirs, find JSONL files, ingest new/modified ones.
        Now loads episode ranges for cross-referencing.
        """
        manifest = {} if force else self._load_manifest()
        # Preserve schema version
        schema = manifest.pop("_schema_version", SCHEMA_VERSION)

        stats = {
            "files_scanned": 0,
            "files_ingested": 0,
            "files_skipped": 0,
            "exchanges_total": 0,
            "errors": [],
        }

        if not PROJECTS_DIR.exists():
            manifest["_schema_version"] = schema
            self._save_manifest(manifest)
            return stats

        # Load episode ranges once for cross-referencing
        episode_ranges = self._load_episode_ranges()

        for project_dir in PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue

            # Skip subagent directories
            if project_dir.name.startswith("."):
                continue

            for jsonl_file in project_dir.glob("*.jsonl"):
                stats["files_scanned"] += 1

                file_str = str(jsonl_file)
                file_stat = os.stat(jsonl_file)

                # Check manifest for changes
                if not force and file_str in manifest:
                    prev = manifest[file_str]
                    if (prev.get("last_modified") == file_stat.st_mtime
                            and prev.get("size_bytes") == file_stat.st_size):
                        stats["files_skipped"] += 1
                        continue

                # Ingest
                try:
                    count = self.ingest_file(file_str, manifest, episode_ranges)
                    stats["files_ingested"] += 1
                    stats["exchanges_total"] += count
                except Exception as e:
                    stats["errors"].append(f"{jsonl_file.name}: {e}")

        self._save_manifest(manifest)
        return stats

    # =========================================================================
    # RECALL — with cosine scoring, recency weighting
    # =========================================================================

    def _recency_factor(self, epoch: float) -> float:
        """
        Calculate recency factor using exponential decay.
        Returns 0.0-1.0 where 1.0 = just happened.
        Half-life: RECENCY_HALF_LIFE_DAYS
        """
        if epoch <= 0:
            return 0.5  # Unknown time gets neutral score

        now = datetime.now().timestamp()
        age_days = max(0, (now - epoch) / 86400)

        import math
        decay = math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)
        return decay

    def recall(
        self,
        query: str,
        n_results: int = 5,
        project: Optional[str] = None,
        recency_weight: float = RECENCY_WEIGHT,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with cosine similarity and recency weighting.

        Cosine distance in ChromaDB: 0 = identical, 2 = opposite.
        Relevance = 1 - distance (gives -1 to 1, but practically 0.3 to 1.0).

        Final score = semantic * (1 - recency_weight) + recency * recency_weight
        """
        if not self.collection:
            return []

        # Fetch more than needed for re-ranking
        fetch_count = min(n_results * 3, 30)

        where_filter = None
        if project:
            where_filter = {"project_dir": project}

        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_count,
            where=where_filter,
        )

        matches = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0

                # Cosine distance → relevance (0 to 1)
                # distance is in [0, 2], so 1 - distance gives [-1, 1]
                # Clamp to [0, 1]
                semantic = max(0.0, min(1.0, 1.0 - distance))

                # Recency factor
                epoch = meta.get("epoch", 0)
                recency = self._recency_factor(epoch)

                # Combined score
                score = semantic * (1.0 - recency_weight) + recency * recency_weight

                matches.append({
                    "content": doc,
                    "relevance": round(semantic, 3),
                    "recency": round(recency, 3),
                    "score": round(score, 3),
                    "session_id": meta.get("session_id", ""),
                    "date": meta.get("date", ""),
                    "hour": meta.get("hour", -1),
                    "project_dir": meta.get("project_dir", ""),
                    "exchange_index": meta.get("exchange_index", 0),
                    "total_exchanges": meta.get("total_exchanges", 0),
                    "user_text_preview": meta.get("user_text_preview", ""),
                    "episode_id": meta.get("episode_id", ""),
                    "epoch": epoch,
                })

        # Re-rank by combined score
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:n_results]

    # =========================================================================
    # CONTEXT WINDOWS — return surrounding exchanges
    # =========================================================================

    def recall_with_context(
        self,
        query: str,
        n_results: int = 3,
        context_size: int = 2,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search conversations and return surrounding exchanges for context.

        Like grep -C but for conversation memory. Returns the matched exchange
        plus `context_size` exchanges before and after from the same session.

        Args:
            query: What to search for
            n_results: Number of primary matches
            context_size: How many exchanges before/after to include
            project: Filter by project dir

        Returns:
            List of matches, each with a "context" field containing nearby exchanges
        """
        # Get primary matches
        matches = self.recall(query, n_results=n_results, project=project)

        if not matches or not self.collection:
            return matches

        # For each match, fetch surrounding exchanges from same session
        for match in matches:
            session_id = match["session_id"]
            exchange_idx = match["exchange_index"]
            total = match["total_exchanges"]

            # Calculate range
            start_idx = max(0, exchange_idx - context_size)
            end_idx = min(total - 1, exchange_idx + context_size)

            if start_idx == end_idx == exchange_idx:
                match["context_before"] = []
                match["context_after"] = []
                continue

            # Fetch all exchanges in range for this session
            try:
                nearby = self.collection.get(
                    where={
                        "$and": [
                            {"session_id": session_id},
                            {"exchange_index": {"$gte": start_idx}},
                            {"exchange_index": {"$lte": end_idx}},
                        ]
                    },
                    include=["documents", "metadatas"],
                )
            except Exception:
                match["context_before"] = []
                match["context_after"] = []
                continue

            # Sort by exchange_index and split into before/after
            context_items = []
            if nearby["documents"]:
                for j, doc in enumerate(nearby["documents"]):
                    meta = nearby["metadatas"][j] if nearby["metadatas"] else {}
                    idx = meta.get("exchange_index", 0)
                    context_items.append({"index": idx, "content": doc})

            context_items.sort(key=lambda x: x["index"])

            match["context_before"] = [
                c["content"] for c in context_items if c["index"] < exchange_idx
            ]
            match["context_after"] = [
                c["content"] for c in context_items if c["index"] > exchange_idx
            ]

        return matches

    # =========================================================================
    # CROSS-REFERENCE QUERIES
    # =========================================================================

    def get_conversations_for_episode(
        self,
        episode_id: str,
        n_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get all conversation exchanges that happened during a specific episode.
        """
        if not self.collection:
            return []

        try:
            results = self.collection.get(
                where={"episode_id": episode_id},
                include=["documents", "metadatas"],
                limit=n_results,
            )
        except Exception:
            return []

        exchanges = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                exchanges.append({
                    "content": doc,
                    "exchange_index": meta.get("exchange_index", 0),
                    "timestamp": meta.get("timestamp", ""),
                    "session_id": meta.get("session_id", ""),
                })

        exchanges.sort(key=lambda x: x["exchange_index"])
        return exchanges

    def get_episodes_for_session(self, session_id: str) -> List[str]:
        """
        Get all episode IDs that overlap with a session.
        """
        if not self.collection:
            return []

        try:
            results = self.collection.get(
                where={"session_id": session_id},
                include=["metadatas"],
            )
        except Exception:
            return []

        episode_ids = set()
        if results["metadatas"]:
            for meta in results["metadatas"]:
                ep_id = meta.get("episode_id", "")
                if ep_id:
                    episode_ids.add(ep_id)

        return sorted(episode_ids)

    # =========================================================================
    # STATS & UTILITIES
    # =========================================================================

    def count(self) -> int:
        if not self.collection:
            return 0
        return self.collection.count()

    def stats(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        sessions = set()
        total_exchanges = 0
        for key, info in manifest.items():
            if key.startswith("_"):
                continue
            sessions.add(info.get("session_id", ""))
            total_exchanges += info.get("exchanges_ingested", 0)

        # Count cross-referenced exchanges
        cross_ref_count = 0
        if self.collection:
            try:
                # $ne doesn't work with empty string in ChromaDB get()
                # Sample and count instead
                sample = self.collection.get(include=["metadatas"], limit=1000)
                if sample["metadatas"]:
                    cross_ref_count = sum(
                        1 for m in sample["metadatas"] if m.get("episode_id")
                    )
            except Exception:
                pass

        return {
            "indexed_exchanges": self.count(),
            "sessions_ingested": len(sessions),
            "manifest_entries": len([k for k in manifest if not k.startswith("_")]),
            "total_exchanges_from_manifest": total_exchanges,
            "cross_referenced": cross_ref_count,
            "schema_version": manifest.get("_schema_version", 1),
        }


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


# CLI
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m memory.conversations [ingest|search|context|stats|test|episode]")
        print("  ingest [--force]       — Index all session files")
        print("  search <query>         — Search past conversations")
        print("  context <query>        — Search with surrounding context")
        print("  episode <episode_id>   — Get conversations for an episode")
        print("  stats                  — Show index statistics")
        print("  test                   — Test extraction on one file")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test":
        import glob
        files = sorted(glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))
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
