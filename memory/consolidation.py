# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Memory consolidation — biological-like memory maintenance.

Merges duplicates, strengthens recalled memories, decays unused ones,
archives dead weight. Called by the overnight brain as post-processing.

The loop: recall → strengthen → decay unused → merge duplicates → archive weak.
"""

import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.paths import get_paths

logger = logging.getLogger("elara.memory.consolidation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.85     # Cosine sim to consider duplicate
DECAY_HALF_LIFE_DAYS = 60       # Importance halves every 60 days without recall
ARCHIVE_THRESHOLD = 0.1         # Below this → archive
RECALL_BOOST = 0.03             # Per-recall importance boost
REINFORCE_BOOST = 0.05          # Merge boost for survivor
MAX_IMPORTANCE = 1.0
PROTECTED_FLOOR = 0.3           # Decay floor for decisions / high-importance
CONTRADICTION_LOW = 0.50        # Minimum similarity to check for contradictions
CONTRADICTION_HIGH = 0.85       # Maximum (above this = duplicate, not contradiction)


# ---------------------------------------------------------------------------
# Recall logging (called from VectorMemory.recall)
# ---------------------------------------------------------------------------

def log_recall(memory_id: str, query: str, relevance: float = 0.0) -> None:
    """Append a recall event to the recall log. Fire-and-forget."""
    try:
        p = get_paths()
        entry = {
            "memory_id": memory_id,
            "query": query,
            "relevance": round(relevance, 4),
            "timestamp": datetime.now().isoformat(),
        }
        with open(p.recall_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug("Recall log write failed: %s", e)


# ---------------------------------------------------------------------------
# Consolidator
# ---------------------------------------------------------------------------

class MemoryConsolidator:
    """Manages memory consolidation: decay, strengthen, merge, archive."""

    def __init__(self):
        self._paths = get_paths()
        self._vm = None  # Lazy-loaded VectorMemory

    @property
    def vm(self):
        if self._vm is None:
            from memory.vector import VectorMemory
            self._vm = VectorMemory()
        return self._vm

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        p = self._paths.consolidation_state
        if p.exists():
            try:
                return json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        p = self._paths.consolidation_state
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2))

    # ------------------------------------------------------------------
    # Recall log reading
    # ------------------------------------------------------------------

    def get_recall_counts(self, since: Optional[str] = None) -> Dict[str, int]:
        """Count recalls per memory_id, optionally since a timestamp."""
        counts: Dict[str, int] = {}
        log_path = self._paths.recall_log
        if not log_path.exists():
            return counts

        cutoff = None
        if since:
            try:
                cutoff = datetime.fromisoformat(since)
            except ValueError:
                pass

        try:
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cutoff:
                    try:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if ts < cutoff:
                            continue
                    except (KeyError, ValueError):
                        continue
                mid = entry.get("memory_id", "")
                if mid:
                    counts[mid] = counts.get(mid, 0) + 1
        except OSError:
            pass

        return counts

    # ------------------------------------------------------------------
    # Archive helpers
    # ------------------------------------------------------------------

    def _archive_memory(self, memory_id: str, content: str,
                        metadata: Dict[str, Any], reason: str = "weak") -> None:
        """Write a memory to the archive JSONL before deletion."""
        try:
            entry = {
                "memory_id": memory_id,
                "content": content,
                "metadata": metadata,
                "archived_at": datetime.now().isoformat(),
                "reason": reason,
            }
            archive_path = self._paths.memory_archive
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with open(archive_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning("Archive write failed for %s: %s", memory_id, e)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def find_duplicates(self, threshold: float = SIMILARITY_THRESHOLD
                        ) -> List[Tuple[str, str, float]]:
        """
        Find duplicate memory pairs above the similarity threshold.
        Returns list of (id_a, id_b, similarity).
        """
        if not self.vm.collection:
            return []

        all_data = self.vm.collection.get(include=["documents", "metadatas"])
        if not all_data["ids"]:
            return []

        ids = all_data["ids"]
        docs = all_data["documents"]

        seen_pairs = set()
        duplicates = []

        for i, doc in enumerate(docs):
            if not doc or not doc.strip():
                continue
            try:
                results = self.vm.collection.query(
                    query_texts=[doc],
                    n_results=min(6, len(ids)),  # self + 5 neighbors
                    include=["distances"],
                )
            except Exception:
                continue

            if not results["ids"] or not results["ids"][0]:
                continue

            for j, neighbor_id in enumerate(results["ids"][0]):
                if neighbor_id == ids[i]:
                    continue  # Skip self-match

                distance = results["distances"][0][j]
                similarity = max(0.0, 1.0 - distance)

                if similarity >= threshold:
                    pair = tuple(sorted([ids[i], neighbor_id]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        duplicates.append((pair[0], pair[1], round(similarity, 4)))

        # Sort by similarity descending
        duplicates.sort(key=lambda x: x[2], reverse=True)
        return duplicates

    def find_contradictions(self) -> List[Dict[str, Any]]:
        """
        Find memory pairs that cover the same topic but say conflicting things.
        Uses semantic similarity (0.50-0.85 range) + LLM classification.
        Falls back to heuristic if Ollama is unavailable.
        """
        if not self.vm.collection:
            return []

        all_data = self.vm.collection.get(include=["documents", "metadatas"])
        if not all_data["ids"]:
            return []

        ids = all_data["ids"]
        docs = all_data["documents"]

        # Find pairs in the contradiction similarity range
        candidates = []
        seen_pairs = set()

        for i, doc in enumerate(docs):
            if not doc or not doc.strip():
                continue
            try:
                results = self.vm.collection.query(
                    query_texts=[doc],
                    n_results=min(10, len(ids)),
                    include=["distances", "documents"],
                )
            except Exception:
                continue

            if not results["ids"] or not results["ids"][0]:
                continue

            for j, neighbor_id in enumerate(results["ids"][0]):
                if neighbor_id == ids[i]:
                    continue

                distance = results["distances"][0][j]
                similarity = max(0.0, 1.0 - distance)

                if CONTRADICTION_LOW <= similarity < CONTRADICTION_HIGH:
                    pair = tuple(sorted([ids[i], neighbor_id]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        candidates.append({
                            "id_a": ids[i],
                            "id_b": neighbor_id,
                            "doc_a": doc,
                            "doc_b": results["documents"][0][j],
                            "similarity": round(similarity, 4),
                        })

        if not candidates:
            return []

        # Classify each candidate pair using LLM
        contradictions = []
        for cand in candidates:
            verdict = self._classify_pair(cand["doc_a"], cand["doc_b"])
            if verdict == "contradicting":
                meta_a = {}
                meta_b = {}
                try:
                    d = self.vm.collection.get(ids=[cand["id_a"]], include=["metadatas"])
                    if d["metadatas"]:
                        meta_a = d["metadatas"][0] or {}
                    d = self.vm.collection.get(ids=[cand["id_b"]], include=["metadatas"])
                    if d["metadatas"]:
                        meta_b = d["metadatas"][0] or {}
                except Exception:
                    pass

                contradictions.append({
                    "id_a": cand["id_a"],
                    "id_b": cand["id_b"],
                    "content_a": cand["doc_a"][:200],
                    "content_b": cand["doc_b"][:200],
                    "similarity": cand["similarity"],
                    "date_a": meta_a.get("date", ""),
                    "date_b": meta_b.get("date", ""),
                    "importance_a": meta_a.get("importance", 0),
                    "importance_b": meta_b.get("importance", 0),
                    "detected_at": datetime.now().isoformat(),
                })

        # Save to file
        if contradictions:
            self._save_contradictions(contradictions)

        return contradictions

    def _classify_pair(self, doc_a: str, doc_b: str) -> str:
        """
        Classify a memory pair as 'same', 'complementary', or 'contradicting'.
        Uses local LLM, falls back to 'unknown' if unavailable.
        'contradicting' means they make CONFLICTING FACTUAL CLAIMS about the same topic.
        """
        # Skip short memories — test messages, greetings, noise
        if len(doc_a.strip()) < 80 or len(doc_b.strip()) < 80:
            return "same"

        try:
            from daemon.llm import query, is_available
            if not is_available():
                return "unknown"

            prompt = (
                f"Two memories from a knowledge base:\n\n"
                f"A: {doc_a[:300]}\n\n"
                f"B: {doc_b[:300]}\n\n"
                f"Do these make CONFLICTING FACTUAL CLAIMS about the same topic? "
                f"For example: one says a project uses dark theme, the other says light theme. "
                f"Or one says a task is done, the other says it's pending.\n\n"
                f"Answer ONLY one word: contradicting, complementary, or same"
            )
            result = query(prompt, temperature=0.1, max_tokens=5)
            if result:
                r = result.lower().strip().rstrip(".")
                if "contradict" in r:
                    return "contradicting"
                if "complement" in r:
                    return "complementary"
                return "same"
            return "unknown"
        except Exception:
            return "unknown"

    def _save_contradictions(self, contradictions: List[Dict[str, Any]]) -> None:
        """Save detected contradictions to file for boot review."""
        p = self._paths.memory_contradictions
        p.parent.mkdir(parents=True, exist_ok=True)

        # Load existing, merge (avoid duplicates by pair key)
        existing = []
        if p.exists():
            try:
                existing = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Key by sorted pair
        existing_keys = set()
        for c in existing:
            key = tuple(sorted([c["id_a"], c["id_b"]]))
            existing_keys.add(key)

        for c in contradictions:
            key = tuple(sorted([c["id_a"], c["id_b"]]))
            if key not in existing_keys:
                existing.append(c)
                existing_keys.add(key)

        p.write_text(json.dumps(existing, indent=2))

    def get_contradictions(self) -> List[Dict[str, Any]]:
        """Load saved contradictions from file."""
        p = self._paths.memory_contradictions
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def resolve_contradiction(self, id_a: str, id_b: str,
                               keep: str = "newer") -> Optional[str]:
        """
        Resolve a contradiction by archiving one memory.
        keep='newer' archives the older one, keep='a' or 'b' picks explicitly.
        Returns the ID of the kept memory, or None on failure.
        """
        if not self.vm.collection:
            return None

        try:
            data_a = self.vm.collection.get(ids=[id_a], include=["documents", "metadatas"])
            data_b = self.vm.collection.get(ids=[id_b], include=["documents", "metadatas"])
        except Exception:
            return None

        if not data_a["ids"] or not data_b["ids"]:
            return None

        meta_a = data_a["metadatas"][0] or {}
        meta_b = data_b["metadatas"][0] or {}

        if keep == "newer":
            ts_a = meta_a.get("timestamp", "")
            ts_b = meta_b.get("timestamp", "")
            # Keep the newer one (higher timestamp)
            if ts_a >= ts_b:
                keep_id, archive_id = id_a, id_b
                archive_doc = data_b["documents"][0]
                archive_meta = meta_b
            else:
                keep_id, archive_id = id_b, id_a
                archive_doc = data_a["documents"][0]
                archive_meta = meta_a
        elif keep == "a":
            keep_id, archive_id = id_a, id_b
            archive_doc = data_b["documents"][0]
            archive_meta = meta_b
        elif keep == "b":
            keep_id, archive_id = id_b, id_a
            archive_doc = data_a["documents"][0]
            archive_meta = meta_a
        else:
            return None

        self._archive_memory(archive_id, archive_doc, archive_meta, reason="contradiction")
        try:
            self.vm.collection.delete(ids=[archive_id])
        except Exception as e:
            logger.warning("Contradiction resolve delete failed: %s", e)
            return None

        # Remove from contradictions file
        contras = self.get_contradictions()
        contras = [c for c in contras
                    if not (sorted([c["id_a"], c["id_b"]]) == sorted([id_a, id_b]))]
        self._paths.memory_contradictions.write_text(json.dumps(contras, indent=2))

        logger.info("Contradiction resolved: kept %s, archived %s", keep_id, archive_id)
        return keep_id

    def merge_memories(self, id_a: str, id_b: str) -> Optional[str]:
        """
        Merge two memories. Keeps the higher-importance survivor.
        Returns survivor ID, or None if merge fails.
        """
        if not self.vm.collection:
            return None

        try:
            data_a = self.vm.collection.get(ids=[id_a], include=["documents", "metadatas"])
            data_b = self.vm.collection.get(ids=[id_b], include=["documents", "metadatas"])
        except Exception as e:
            logger.warning("Merge fetch failed: %s", e)
            return None

        if not data_a["ids"] or not data_b["ids"]:
            logger.debug("One or both memories not found for merge: %s, %s", id_a, id_b)
            return None

        doc_a = data_a["documents"][0]
        doc_b = data_b["documents"][0]
        meta_a = data_a["metadatas"][0] or {}
        meta_b = data_b["metadatas"][0] or {}

        imp_a = meta_a.get("importance", 0.5)
        imp_b = meta_b.get("importance", 0.5)

        # Survivor = higher importance
        if imp_a >= imp_b:
            survivor_id, absorbed_id = id_a, id_b
            survivor_doc, absorbed_doc = doc_a, doc_b
            survivor_meta, absorbed_meta = dict(meta_a), dict(meta_b)
            survivor_imp = imp_a
        else:
            survivor_id, absorbed_id = id_b, id_a
            survivor_doc, absorbed_doc = doc_b, doc_a
            survivor_meta, absorbed_meta = dict(meta_b), dict(meta_a)
            survivor_imp = imp_b

        # Append absorbed content if substantially different
        absorbed_unique_ratio = len(absorbed_doc) / max(len(survivor_doc), 1)
        if absorbed_unique_ratio > 0.5 and absorbed_doc.strip() != survivor_doc.strip():
            merged_content = survivor_doc.rstrip() + f"\n[Also: {absorbed_doc.strip()}]"
        else:
            merged_content = survivor_doc

        # Update survivor metadata
        new_importance = min(MAX_IMPORTANCE, survivor_imp + REINFORCE_BOOST)
        survivor_meta["importance"] = new_importance
        # Track all absorbed IDs (supports multi-hop merges)
        prev_merged = survivor_meta.get("merged_from", "")
        if prev_merged:
            survivor_meta["merged_from"] = f"{prev_merged},{absorbed_id}"
        else:
            survivor_meta["merged_from"] = absorbed_id
        survivor_meta["merge_date"] = datetime.now().isoformat()

        # Use the older timestamp
        ts_a = meta_a.get("timestamp", "")
        ts_b = meta_b.get("timestamp", "")
        if ts_a and ts_b:
            survivor_meta["timestamp"] = min(ts_a, ts_b)

        # Archive absorbed first
        self._archive_memory(absorbed_id, absorbed_doc, absorbed_meta, reason="merged")

        # Update survivor
        try:
            self.vm.collection.update(
                ids=[survivor_id],
                documents=[merged_content],
                metadatas=[survivor_meta],
            )
        except Exception as e:
            logger.warning("Survivor update failed: %s", e)
            return None

        # Delete absorbed
        try:
            self.vm.collection.delete(ids=[absorbed_id])
        except Exception as e:
            logger.warning("Absorbed delete failed: %s", e)

        # Emit event
        try:
            from daemon.events import bus, Events
            bus.emit(Events.MEMORY_CONSOLIDATED, {
                "survivor_id": survivor_id,
                "absorbed_id": absorbed_id,
                "new_importance": new_importance,
            }, source="consolidation")
        except Exception:
            pass

        logger.info("Merged %s into %s (importance %.2f → %.2f)",
                     absorbed_id, survivor_id, survivor_imp, new_importance)
        return survivor_id

    def apply_decay(self, last_run: Optional[str] = None) -> Dict[str, Any]:
        """
        Decay importance of memories not recalled since last run.
        Protected: decisions never drop below PROTECTED_FLOOR.
        Protected: originally >= 0.8 importance never drop below PROTECTED_FLOOR.
        """
        if not self.vm.collection:
            return {"decayed": 0}

        recall_counts = self.get_recall_counts(since=last_run)
        all_data = self.vm.collection.get(include=["metadatas"])

        if not all_data["ids"]:
            return {"decayed": 0}

        now = datetime.now()
        days_since_run = 7  # Default if no last_run
        if last_run:
            try:
                days_since_run = (now - datetime.fromisoformat(last_run)).days
            except ValueError:
                pass
        days_since_run = max(1, days_since_run)

        decayed_count = 0
        updates_ids = []
        updates_meta = []

        for i, mid in enumerate(all_data["ids"]):
            if mid in recall_counts:
                continue  # Recalled recently — skip decay

            meta = all_data["metadatas"][i] or {}
            current_imp = meta.get("importance", 0.5)
            mem_type = meta.get("type", "")

            # Decay: importance *= 0.5^(days / half_life)
            decay_factor = math.pow(0.5, days_since_run / DECAY_HALF_LIFE_DAYS)
            new_imp = current_imp * decay_factor

            # Floor protections
            is_decision = mem_type == "decision"
            originally_high = current_imp >= 0.8 or meta.get("importance_original", 0) >= 0.8
            if is_decision or originally_high:
                new_imp = max(new_imp, PROTECTED_FLOOR)

            if abs(new_imp - current_imp) > 0.001:
                new_meta = dict(meta)
                # Preserve original importance on first decay
                if "importance_original" not in new_meta:
                    new_meta["importance_original"] = current_imp
                new_meta["importance"] = round(new_imp, 4)
                new_meta["last_decayed"] = now.isoformat()
                updates_ids.append(mid)
                updates_meta.append(new_meta)
                decayed_count += 1

        # Batch update
        if updates_ids:
            try:
                self.vm.collection.update(ids=updates_ids, metadatas=updates_meta)
            except Exception as e:
                logger.warning("Decay batch update failed: %s", e)
                return {"decayed": 0, "error": str(e)}

        return {"decayed": decayed_count}

    def strengthen_recalled(self, last_run: Optional[str] = None) -> Dict[str, Any]:
        """Boost importance of memories that were recalled since last run."""
        if not self.vm.collection:
            return {"strengthened": 0}

        recall_counts = self.get_recall_counts(since=last_run)
        if not recall_counts:
            return {"strengthened": 0}

        # Fetch current metadata for recalled memories
        recalled_ids = list(recall_counts.keys())
        try:
            data = self.vm.collection.get(ids=recalled_ids, include=["metadatas"])
        except Exception:
            return {"strengthened": 0}

        if not data["ids"]:
            return {"strengthened": 0}

        strengthened_count = 0
        updates_ids = []
        updates_meta = []

        for i, mid in enumerate(data["ids"]):
            meta = data["metadatas"][i] or {}
            current_imp = meta.get("importance", 0.5)
            count = recall_counts.get(mid, 0)
            boost = RECALL_BOOST * count
            new_imp = min(MAX_IMPORTANCE, current_imp + boost)

            if new_imp > current_imp:
                new_meta = dict(meta)
                new_meta["importance"] = round(new_imp, 4)
                new_meta["last_recalled_boost"] = datetime.now().isoformat()
                new_meta["recall_count"] = meta.get("recall_count", 0) + count
                updates_ids.append(mid)
                updates_meta.append(new_meta)
                strengthened_count += 1

        if updates_ids:
            try:
                self.vm.collection.update(ids=updates_ids, metadatas=updates_meta)
            except Exception as e:
                logger.warning("Strengthen batch update failed: %s", e)
                return {"strengthened": 0, "error": str(e)}

        return {"strengthened": strengthened_count}

    def archive_weak(self) -> Dict[str, Any]:
        """
        Archive memories with importance < ARCHIVE_THRESHOLD.
        Never archives decisions or originally high-importance memories.
        """
        if not self.vm.collection:
            return {"archived": 0}

        all_data = self.vm.collection.get(include=["documents", "metadatas"])
        if not all_data["ids"]:
            return {"archived": 0}

        to_archive = []
        for i, mid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i] or {}
            imp = meta.get("importance", 0.5)
            mem_type = meta.get("type", "")

            if imp >= ARCHIVE_THRESHOLD:
                continue

            # Never archive protected types
            if mem_type == "decision":
                continue
            if meta.get("importance_original", 0) >= 0.8:
                continue

            to_archive.append((mid, all_data["documents"][i], meta))

        archived_count = 0
        for mid, doc, meta in to_archive:
            self._archive_memory(mid, doc, meta, reason="weak")
            try:
                self.vm.collection.delete(ids=[mid])
                archived_count += 1

                # Emit event
                try:
                    from daemon.events import bus, Events
                    bus.emit(Events.MEMORY_ARCHIVED, {
                        "memory_id": mid,
                        "importance": meta.get("importance", 0),
                        "reason": "weak",
                    }, source="consolidation")
                except Exception:
                    pass

            except Exception as e:
                logger.warning("Archive delete failed for %s: %s", mid, e)

        return {"archived": archived_count}

    def get_at_risk(self, threshold: float = 0.2) -> List[Dict[str, Any]]:
        """Return memories with importance below threshold (at risk of archival)."""
        if not self.vm.collection:
            return []

        all_data = self.vm.collection.get(include=["documents", "metadatas"])
        if not all_data["ids"]:
            return []

        at_risk = []
        for i, mid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i] or {}
            imp = meta.get("importance", 0.5)
            if imp < threshold:
                at_risk.append({
                    "memory_id": mid,
                    "content": (all_data["documents"][i] or "")[:80],
                    "importance": imp,
                    "type": meta.get("type", ""),
                    "date": meta.get("date", ""),
                })

        at_risk.sort(key=lambda x: x["importance"])
        return at_risk

    # ------------------------------------------------------------------
    # Full consolidation pass
    # ------------------------------------------------------------------

    def consolidate(self) -> Dict[str, Any]:
        """
        Run a full consolidation pass:
        1. Get recall counts
        2. Strengthen recalled memories
        3. Decay unrequested memories
        4. Find and merge duplicates
        5. Archive weak memories
        6. Save state
        """
        state = self._load_state()
        last_run = state.get("last_run")
        result: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}

        # 1. Strengthen recalled
        try:
            strengthen_result = self.strengthen_recalled(last_run=last_run)
            result["strengthened"] = strengthen_result.get("strengthened", 0)
        except Exception as e:
            logger.warning("Strengthen phase failed: %s", e)
            result["strengthened"] = 0

        # 2. Decay unrequested
        try:
            decay_result = self.apply_decay(last_run=last_run)
            result["decayed"] = decay_result.get("decayed", 0)
        except Exception as e:
            logger.warning("Decay phase failed: %s", e)
            result["decayed"] = 0

        # 3. Find and merge duplicates
        try:
            duplicates = self.find_duplicates()
            merged_count = 0
            for id_a, id_b, sim in duplicates:
                survivor = self.merge_memories(id_a, id_b)
                if survivor:
                    merged_count += 1
            result["merged"] = merged_count
            result["duplicate_pairs_found"] = len(duplicates)
        except Exception as e:
            logger.warning("Merge phase failed: %s", e)
            result["merged"] = 0

        # 4. Archive weak
        try:
            archive_result = self.archive_weak()
            result["archived"] = archive_result.get("archived", 0)
        except Exception as e:
            logger.warning("Archive phase failed: %s", e)
            result["archived"] = 0

        # 5. Contradiction detection
        try:
            contradictions = self.find_contradictions()
            result["contradictions_found"] = len(contradictions)
        except Exception as e:
            logger.warning("Contradiction detection failed: %s", e)
            result["contradictions_found"] = 0

        # 6. Final count
        try:
            result["memories_after"] = self.vm.collection.count() if self.vm.collection else 0
        except Exception:
            result["memories_after"] = -1

        # 6. Save state
        state["last_run"] = result["timestamp"]
        state["runs"] = state.get("runs", 0) + 1
        state["last_result"] = result
        self._save_state(state)

        logger.info(
            "Consolidation complete: strengthened=%d, decayed=%d, merged=%d, archived=%d, contradictions=%d, remaining=%d",
            result.get("strengthened", 0), result.get("decayed", 0),
            result.get("merged", 0), result.get("archived", 0),
            result.get("contradictions_found", 0), result.get("memories_after", -1),
        )

        return result

    def stats(self) -> Dict[str, Any]:
        """Return consolidation statistics."""
        state = self._load_state()
        memory_count = 0
        try:
            if self.vm.collection:
                memory_count = self.vm.collection.count()
        except Exception:
            pass

        recall_log_size = 0
        recall_log_path = self._paths.recall_log
        if recall_log_path.exists():
            try:
                recall_log_size = sum(1 for _ in recall_log_path.read_text().splitlines() if _.strip())
            except OSError:
                pass

        archive_size = 0
        archive_path = self._paths.memory_archive
        if archive_path.exists():
            try:
                archive_size = sum(1 for _ in archive_path.read_text().splitlines() if _.strip())
            except OSError:
                pass

        at_risk = self.get_at_risk(threshold=0.2)
        contradictions = self.get_contradictions()

        return {
            "memory_count": memory_count,
            "recall_log_entries": recall_log_size,
            "archive_size": archive_size,
            "at_risk_count": len(at_risk),
            "contradictions_count": len(contradictions),
            "total_runs": state.get("runs", 0),
            "last_run": state.get("last_run"),
            "last_result": state.get("last_result"),
        }


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_consolidator: Optional[MemoryConsolidator] = None


def get_consolidator() -> MemoryConsolidator:
    """Return the global MemoryConsolidator singleton."""
    global _consolidator
    if _consolidator is None:
        _consolidator = MemoryConsolidator()
    return _consolidator


def consolidate() -> Dict[str, Any]:
    """Run a full consolidation pass. Convenience wrapper."""
    return get_consolidator().consolidate()


def get_consolidation_stats() -> Dict[str, Any]:
    """Get consolidation stats. Convenience wrapper."""
    return get_consolidator().stats()
