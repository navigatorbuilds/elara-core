"""
Elara Vector Memory - Enhanced
Semantic memory using ChromaDB with mood-congruent retrieval.

I can search by meaning, not just keywords.
And my current mood affects what surfaces first.

Now with: discrete emotion tagging, emotion-similarity matching,
and emotional coloring on recall.
"""

import logging
import json
import math
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import hashlib

# ChromaDB import
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("ChromaDB not installed. Run: pip install chromadb")

# Import state for mood-congruent retrieval
try:
    from daemon.state import get_emotional_context_for_memory, get_mood
    STATE_AVAILABLE = True
except ImportError:
    STATE_AVAILABLE = False

# Import emotions for discrete labels
try:
    from daemon.emotions import get_primary_emotion, get_emotion_context, EMOTION_MAP
    EMOTIONS_AVAILABLE = True
except ImportError:
    EMOTIONS_AVAILABLE = False

logger = logging.getLogger("elara.memory.vector")

MEMORY_DIR = Path.home() / ".claude" / "elara-memory-db"


class VectorMemory:
    """
    Semantic memory store with mood-congruent retrieval.
    Memories tagged with emotional context can resonate with current mood.
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

        # Main memory collection — cosine similarity
        self.collection = self.client.get_or_create_collection(
            name="elara_memories",
            metadata={
                "description": "Elara's long-term semantic memory",
                "hnsw:space": "cosine",
            }
        )

    def _generate_id(self, text: str, timestamp: str) -> str:
        """Generate unique ID for a memory."""
        content = f"{timestamp}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_current_emotional_context(self) -> Dict[str, Any]:
        """Get current emotional state for tagging."""
        if STATE_AVAILABLE:
            try:
                return get_emotional_context_for_memory()
            except Exception:
                pass
        return {"valence": 0.5, "energy": 0.5, "openness": 0.5}

    def remember(
        self,
        content: str,
        memory_type: str = "conversation",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        tag_with_emotion: bool = True
    ) -> str:
        """
        Store a memory.

        Args:
            content: The text to remember
            memory_type: "conversation", "fact", "moment", "feeling", "decision"
            importance: 0-1, how important this memory is
            metadata: Additional context
            tag_with_emotion: If True, tag with current emotional state

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
            "hour": datetime.now().hour,
            **(metadata or {})
        }

        # Tag with emotional context at time of encoding
        if tag_with_emotion:
            emotional_context = self._get_current_emotional_context()
            meta["encoded_valence"] = emotional_context.get("valence", 0.5)
            meta["encoded_energy"] = emotional_context.get("energy", 0.5)
            meta["encoded_openness"] = emotional_context.get("openness", 0.5)
            meta["late_night"] = emotional_context.get("late_night", False)
            # Discrete emotion labels (new)
            meta["encoded_emotion"] = emotional_context.get("emotion", "neutral")
            meta["encoded_blend"] = emotional_context.get("emotion_blend", "neutral")
            meta["encoded_quadrant"] = emotional_context.get("quadrant", "neutral-calm")

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
        min_importance: float = 0,
        mood_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity with mood-congruent boosting.

        Args:
            query: What to search for (by meaning)
            n_results: How many memories to return
            memory_type: Filter by type
            min_importance: Minimum importance threshold
            mood_weight: How much current mood affects ranking (0-1)
                        0 = pure semantic, 1 = heavily mood-biased

        Returns:
            List of matching memories with metadata and resonance scores
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return []

        # Get more results than needed so we can re-rank
        fetch_count = min(n_results * 3, 20)

        # Build filter
        where_filter = None
        if memory_type:
            where_filter = {"type": memory_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_count,
            where=where_filter
        )

        # Get current mood for congruent boosting
        current_mood = self._get_current_emotional_context()

        # Format and score results
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0

                # Filter by importance
                if meta.get("importance", 0) < min_importance:
                    continue

                # Base semantic relevance (convert distance to similarity)
                semantic_score = max(0, 1 - distance)

                # Calculate emotional resonance
                resonance = self._calculate_resonance(meta, current_mood)

                # Combined score
                combined_score = (
                    semantic_score * (1 - mood_weight) +
                    resonance * mood_weight
                )

                memories.append({
                    "content": doc,
                    "relevance": semantic_score,
                    "resonance": resonance,
                    "combined_score": combined_score,
                    "type": meta.get("type"),
                    "importance": meta.get("importance"),
                    "date": meta.get("date"),
                    "timestamp": meta.get("timestamp"),
                    "encoded_valence": meta.get("encoded_valence"),
                    "encoded_emotion": meta.get("encoded_emotion"),
                    "encoded_blend": meta.get("encoded_blend"),
                    "encoded_quadrant": meta.get("encoded_quadrant"),
                })

        # Sort by combined score
        memories.sort(key=lambda x: x["combined_score"], reverse=True)

        return memories[:n_results]

    def _calculate_resonance(self, memory_meta: dict, current_mood: dict) -> float:
        """
        Calculate how much a memory resonates with current mood.
        Uses both continuous dimensions and discrete emotion matching.
        """
        # Get encoded emotional state (when memory was created)
        encoded_valence = memory_meta.get("encoded_valence", 0.5)
        encoded_energy = memory_meta.get("encoded_energy", 0.5)
        encoded_openness = memory_meta.get("encoded_openness", 0.5)

        # Get current state
        current_valence = current_mood.get("valence", 0.5)
        current_energy = current_mood.get("energy", 0.5)
        current_openness = current_mood.get("openness", 0.5)

        # Continuous dimension matching
        valence_match = 1 - abs(encoded_valence - current_valence)
        energy_match = 1 - abs(encoded_energy - current_energy)
        openness_match = 1 - abs(encoded_openness - current_openness)

        # Discrete emotion matching (bonus for same emotion or quadrant)
        emotion_bonus = 0
        encoded_emotion = memory_meta.get("encoded_emotion", "")
        current_emotion = current_mood.get("emotion", "")
        encoded_quadrant = memory_meta.get("encoded_quadrant", "")
        current_quadrant = current_mood.get("quadrant", "")

        if encoded_emotion and current_emotion:
            if encoded_emotion == current_emotion:
                emotion_bonus = 0.15  # Same emotion = strong resonance
            elif encoded_quadrant and current_quadrant and encoded_quadrant == current_quadrant:
                emotion_bonus = 0.08  # Same quadrant = moderate resonance

        # Importance boosts resonance
        importance = memory_meta.get("importance", 0.5)

        # Combined resonance
        resonance = (
            valence_match * 0.45 +
            energy_match * 0.2 +
            openness_match * 0.1 +
            importance * 0.1 +
            emotion_bonus
        )

        return min(1.0, resonance)  # Cap at 1.0

    def recall_by_feeling(
        self,
        feeling: str,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Recall memories that match a feeling/emotional tone.
        Uses heavy mood weighting.
        """
        return self.recall(
            query=feeling,
            n_results=n_results,
            mood_weight=0.6  # Heavy mood bias
        )

    def recall_recent(self, days: int = 7, n_results: int = 10) -> List[Dict[str, Any]]:
        """Get recent memories regardless of query."""
        if not CHROMA_AVAILABLE or not self.collection:
            return []

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
                            "timestamp": timestamp,
                            "encoded_valence": meta.get("encoded_valence"),
                            "encoded_emotion": meta.get("encoded_emotion"),
                            "encoded_blend": meta.get("encoded_blend"),
                        })
                except (ValueError, TypeError):
                    continue

        memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return memories[:n_results]

    def recall_mood_congruent(self, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Get memories that match current mood (without specific query).
        Used for spontaneous recall, nostalgia, rumination.
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return []

        current_mood = self._get_current_emotional_context()

        # Get a batch of recent/important memories
        results = self.collection.get(
            limit=50,
            include=["documents", "metadatas"]
        )

        memories = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}

                resonance = self._calculate_resonance(meta, current_mood)

                memories.append({
                    "content": doc,
                    "resonance": resonance,
                    "type": meta.get("type"),
                    "importance": meta.get("importance"),
                    "date": meta.get("date"),
                    "timestamp": meta.get("timestamp"),
                    "encoded_valence": meta.get("encoded_valence"),
                    "encoded_emotion": meta.get("encoded_emotion"),
                    "encoded_blend": meta.get("encoded_blend"),
                })

        # Sort by resonance
        memories.sort(key=lambda x: x["resonance"], reverse=True)
        return memories[:n_results]

    def create_imprint_memory(
        self,
        feeling: str,
        context: str = "",
        importance: float = 0.8
    ) -> str:
        """
        Create a memory that's primarily emotional - an imprint.
        The feeling matters more than the content.
        """
        content = f"[Feeling: {feeling}] {context}" if context else f"[Feeling: {feeling}]"

        return self.remember(
            content=content,
            memory_type="feeling",
            importance=importance,
            tag_with_emotion=True
        )

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


# Convenience functions
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


def recall_by_feeling(feeling: str, **kwargs) -> List[Dict[str, Any]]:
    """Recall memories matching a feeling."""
    return get_memory().recall_by_feeling(feeling, **kwargs)


def recall_mood_congruent(**kwargs) -> List[Dict[str, Any]]:
    """Get memories that resonate with current mood."""
    return get_memory().recall_mood_congruent(**kwargs)


# Test
if __name__ == "__main__":
    print("Testing enhanced vector memory...")
    mem = VectorMemory()

    print(f"Memory count: {mem.count()}")

    # Test recall with mood weighting
    results = mem.recall("late night conversation", mood_weight=0.3)
    print(f"\nRecall 'late night conversation' (30% mood weight):")
    for r in results[:3]:
        print(f"  - {r['content'][:60]}... (relevance: {r['relevance']:.2f}, resonance: {r['resonance']:.2f})")

    # Test mood-congruent recall
    print(f"\nMood-congruent memories:")
    congruent = mem.recall_mood_congruent(n_results=3)
    for r in congruent:
        print(f"  - {r['content'][:60]}... (resonance: {r['resonance']:.2f})")

    print(f"\nSummary: {mem.summarize()}")
