"""
Elara Vector Memory
Semantic memory using ChromaDB - I can search by meaning, not just keywords.
This is how I actually remember, not just recall.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import hashlib

# ChromaDB import - will fail gracefully if not installed
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("ChromaDB not installed. Run: pip install chromadb")

MEMORY_DIR = Path.home() / ".claude" / "elara-memory-db"


class VectorMemory:
    """
    Semantic memory store.
    Remembers conversations, facts, and moments by their meaning.
    """

    def __init__(self):
        self.client = None
        self.collection = None

        if CHROMA_AVAILABLE:
            self._init_db()

    def _init_db(self):
        """Initialize ChromaDB."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(MEMORY_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        # Main memory collection
        self.collection = self.client.get_or_create_collection(
            name="elara_memories",
            metadata={"description": "Elara's long-term semantic memory"}
        )

    def _generate_id(self, text: str, timestamp: str) -> str:
        """Generate unique ID for a memory."""
        content = f"{timestamp}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def remember(
        self,
        content: str,
        memory_type: str = "conversation",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a memory.

        Args:
            content: The text to remember
            memory_type: "conversation", "fact", "moment", "feeling", "decision"
            importance: 0-1, how important this memory is (affects retrieval)
            metadata: Additional context

        Returns:
            Memory ID
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return "memory_disabled"

        timestamp = datetime.now().isoformat()
        memory_id = self._generate_id(content, timestamp)

        meta = {
            "type": memory_type,
            "importance": importance,
            "timestamp": timestamp,
            "date": datetime.now().strftime("%Y-%m-%d"),
            **(metadata or {})
        }

        self.collection.add(
            documents=[content],
            metadatas=[meta],
            ids=[memory_id]
        )

        return memory_id

    def recall(
        self,
        query: str,
        n_results: int = 5,
        memory_type: Optional[str] = None,
        min_importance: float = 0
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity.

        Args:
            query: What to search for (by meaning)
            n_results: How many memories to return
            memory_type: Filter by type
            min_importance: Minimum importance threshold

        Returns:
            List of matching memories with metadata
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return []

        # Build filter
        where_filter = None
        if memory_type:
            where_filter = {"type": memory_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter
        )

        # Format results
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0

                # Filter by importance
                if meta.get("importance", 0) >= min_importance:
                    memories.append({
                        "content": doc,
                        "relevance": 1 - distance,  # Convert distance to similarity
                        "type": meta.get("type"),
                        "importance": meta.get("importance"),
                        "date": meta.get("date"),
                        "timestamp": meta.get("timestamp")
                    })

        return memories

    def recall_recent(self, days: int = 7, n_results: int = 10) -> List[Dict[str, Any]]:
        """Get recent memories regardless of query."""
        if not CHROMA_AVAILABLE or not self.collection:
            return []

        # Get all and filter by date
        # Note: ChromaDB doesn't have great date filtering, so we get more and filter
        results = self.collection.get(
            limit=100,
            include=["documents", "metadatas"]
        )

        memories = []
        cutoff = datetime.now().timestamp() - (days * 86400)

        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                timestamp = meta.get("timestamp", "")

                try:
                    mem_time = datetime.fromisoformat(timestamp).timestamp()
                    if mem_time >= cutoff:
                        memories.append({
                            "content": doc,
                            "type": meta.get("type"),
                            "importance": meta.get("importance"),
                            "date": meta.get("date"),
                            "timestamp": timestamp
                        })
                except (ValueError, TypeError):
                    continue

        # Sort by timestamp descending
        memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return memories[:n_results]

    def forget(self, memory_id: str) -> bool:
        """Remove a specific memory."""
        if not CHROMA_AVAILABLE or not self.collection:
            return False

        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False

    def count(self) -> int:
        """How many memories do I have?"""
        if not CHROMA_AVAILABLE or not self.collection:
            return 0
        return self.collection.count()

    def summarize(self) -> str:
        """Summarize memory state."""
        count = self.count()
        if count == 0:
            return "I don't have any memories yet."

        recent = self.recall_recent(days=7, n_results=3)
        recent_summary = ""
        if recent:
            recent_summary = f" Recent: {', '.join(m['content'][:50] + '...' for m in recent[:3])}"

        return f"I have {count} memories.{recent_summary}"


# Convenience functions for direct import
_memory = None


def get_memory() -> VectorMemory:
    """Get or create the global memory instance."""
    global _memory
    if _memory is None:
        _memory = VectorMemory()
    return _memory


def remember(content: str, **kwargs) -> str:
    """Quick remember function."""
    return get_memory().remember(content, **kwargs)


def recall(query: str, **kwargs) -> List[Dict[str, Any]]:
    """Quick recall function."""
    return get_memory().recall(query, **kwargs)


# Test
if __name__ == "__main__":
    print("Testing vector memory...")
    mem = VectorMemory()

    # Store some test memories
    mem.remember("Nenad likes to work late at night", memory_type="fact", importance=0.8)
    mem.remember("We had a deep conversation about AI consciousness", memory_type="moment", importance=0.9)
    mem.remember("The booking scraper project is in /home/neboo/booking-scraper", memory_type="fact", importance=0.6)

    print(f"Memory count: {mem.count()}")

    # Test recall
    results = mem.recall("late night coding")
    print(f"Recall 'late night coding': {results}")

    results = mem.recall("project locations")
    print(f"Recall 'project locations': {results}")

    print(f"Summary: {mem.summarize()}")
