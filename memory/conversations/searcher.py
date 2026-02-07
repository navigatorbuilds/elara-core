"""
Elara Conversation Memory — Search/Recall mixin.

Cosine similarity search with recency weighting and context windows.
"""

import math
from datetime import datetime
from typing import List, Optional, Dict, Any

from memory.conversations.core import RECENCY_HALF_LIFE_DAYS, RECENCY_WEIGHT


class SearcherMixin:
    """Mixin providing recall and context window capabilities."""

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
