# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Conversation Memory — Ingestion mixin.

Extracts exchanges from JSONL session files and indexes them in ChromaDB.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from memory.conversations.core import PROJECTS_DIR, SCHEMA_VERSION


class IngesterMixin:
    """Mixin providing extraction and ingestion capabilities."""

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

    def ingest_exchange(
        self,
        user_text: str,
        assistant_text: str,
        timestamp: str,
        session_id: str,
        exchange_index: int = -1,
    ) -> bool:
        """
        Ingest a single exchange into ChromaDB.
        Used by Overwatch for mid-session micro-ingestion.
        """
        if not self.collection:
            return False

        doc = f"User: {user_text}\n\nElara: {assistant_text}"
        if len(doc) > 2000:
            doc = doc[:2000]

        ex_id = self._generate_id(session_id, exchange_index, timestamp)

        date_str = ""
        hour = -1
        epoch = 0.0
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                hour = dt.hour
                epoch = dt.timestamp()
            except (ValueError, TypeError):
                pass

        meta = {
            "session_id": session_id,
            "project_dir": "",
            "project_cwd": "",
            "timestamp": timestamp,
            "date": date_str,
            "hour": hour,
            "epoch": epoch,
            "exchange_index": exchange_index,
            "total_exchanges": -1,
            "user_text_preview": user_text[:100],
            "episode_id": "",
        }

        try:
            self.collection.add(ids=[ex_id], documents=[doc], metadatas=[meta])
            return True
        except Exception:
            return False
