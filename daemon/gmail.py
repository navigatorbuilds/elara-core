# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Gmail — Email management via Gmail API.

Read, search, triage, send, archive, label, and semantic search
across indexed emails. Uses OAuth2 for auth, ChromaDB for indexing,
and local LLM for triage/summarization.

Storage:
- Credentials: ~/.claude/elara-gmail-credentials.json (OAuth client secret)
- Token:       ~/.claude/elara-gmail-token.json (user auth, auto-refreshed)
- Index:       ~/.claude/elara-gmail-db/ (ChromaDB collection, cosine)
- Cache:       ~/.claude/elara-gmail-cache.json (sync state)

OAuth scope: gmail.modify (read + send + archive + label, no permanent delete)
"""

import base64
import hashlib
import json
import logging
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Any

from core.paths import get_paths
from daemon.schemas import GmailCache, load_validated, save_validated, atomic_write_json

logger = logging.getLogger("elara.gmail")

# Paths
_p = get_paths()
CREDENTIALS_FILE = _p.gmail_credentials
TOKEN_FILE = _p.gmail_token
GMAIL_DB_DIR = _p.gmail_db
CACHE_FILE = _p.gmail_cache

# Gmail API scope
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Lazy-loaded service
_service = None


# ============================================================================
# Auth layer
# ============================================================================

def is_authorized() -> bool:
    """Check if a valid token exists."""
    if not TOKEN_FILE.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token)
    except Exception as e:
        logger.warning("Failed to check Gmail authorization: %s", e)
        return False


def authorize() -> Dict[str, Any]:
    """
    Run OAuth2 flow. Opens browser for consent.
    Returns status dict.
    """
    if not CREDENTIALS_FILE.exists():
        return {
            "status": "error",
            "message": f"Credentials file not found at {CREDENTIALS_FILE}. "
                       "Download OAuth client JSON from Google Cloud Console.",
        }

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        return {"status": "ok", "message": "Gmail authorized successfully."}
    except Exception as e:
        return {"status": "error", "message": f"Auth failed: {e}"}


def _get_service():
    """Get cached Gmail API service, auto-refreshing token if needed."""
    global _service
    if _service is not None:
        return _service

    if not TOKEN_FILE.exists():
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())

        if not creds.valid:
            return None

        _service = build("gmail", "v1", credentials=creds)
        return _service
    except Exception as e:
        logger.warning(f"Gmail service init failed: {e}")
        return None


# ============================================================================
# Read operations
# ============================================================================

def list_labels() -> List[Dict[str, str]]:
    """List all Gmail labels."""
    service = _get_service()
    if not service:
        return []

    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        return [{"id": l["id"], "name": l["name"]} for l in labels]
    except Exception as e:
        logger.warning(f"list_labels failed: {e}")
        return []


def fetch_messages(
    query: str = "",
    label: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch messages matching criteria. Returns list of message summaries.
    """
    service = _get_service()
    if not service:
        return []

    try:
        kwargs: Dict[str, Any] = {
            "userId": "me",
            "maxResults": min(max_results, 50),
        }
        if query:
            kwargs["q"] = query
        if label:
            kwargs["labelIds"] = [label]

        results = service.users().messages().list(**kwargs).execute()
        message_ids = results.get("messages", [])

        messages = []
        for msg_ref in message_ids:
            msg = _get_message_summary(service, msg_ref["id"])
            if msg:
                messages.append(msg)

        return messages
    except Exception as e:
        logger.warning(f"fetch_messages failed: {e}")
        return []


def _get_message_summary(service, message_id: str) -> Optional[Dict[str, Any]]:
    """Get a lightweight message summary (headers + snippet)."""
    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "labels": msg.get("labelIds", []),
            "is_unread": "UNREAD" in msg.get("labelIds", []),
        }
    except Exception as e:
        logger.debug(f"_get_message_summary({message_id}) failed: {e}")
        return None


def get_message(message_id: str) -> Optional[Dict[str, Any]]:
    """Get full message details including body."""
    service = _get_service()
    if not service:
        return None

    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "labels": msg.get("labelIds", []),
            "is_unread": "UNREAD" in msg.get("labelIds", []),
            "body": body,
        }
    except Exception as e:
        logger.warning(f"get_message({message_id}) failed: {e}")
        return None


def _extract_body(payload: Dict) -> str:
    """Extract text body from message payload (handles multipart)."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    # Fallback: try HTML
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    # Nested multipart
    for part in parts:
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    return ""


def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get full thread with all messages."""
    service = _get_service()
    if not service:
        return None

    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()

        messages = []
        for msg in thread.get("messages", []):
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            messages.append({
                "id": msg["id"],
                "snippet": msg.get("snippet", ""),
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "labels": msg.get("labelIds", []),
            })

        return {
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": messages,
        }
    except Exception as e:
        logger.warning(f"get_thread({thread_id}) failed: {e}")
        return None


# ============================================================================
# Write operations
# ============================================================================

def send_message(
    to: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an email or reply to a thread."""
    service = _get_service()
    if not service:
        return {"status": "error", "message": "Not authorized."}

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body: Dict[str, Any] = {"raw": raw}

        if reply_to:
            send_body["threadId"] = reply_to

        result = service.users().messages().send(
            userId="me", body=send_body,
        ).execute()

        return {
            "status": "ok",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
        }
    except Exception as e:
        return {"status": "error", "message": f"Send failed: {e}"}


def modify_message(
    message_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add/remove labels on a message. Use to archive, star, mark read, etc."""
    service = _get_service()
    if not service:
        return {"status": "error", "message": "Not authorized."}

    try:
        body: Dict[str, Any] = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        service.users().messages().modify(
            userId="me", id=message_id, body=body,
        ).execute()

        return {"status": "ok", "message_id": message_id}
    except Exception as e:
        return {"status": "error", "message": f"Modify failed: {e}"}


def trash_message(message_id: str) -> Dict[str, Any]:
    """Move a message to trash."""
    service = _get_service()
    if not service:
        return {"status": "error", "message": "Not authorized."}

    try:
        service.users().messages().trash(userId="me", id=message_id).execute()
        return {"status": "ok", "message_id": message_id}
    except Exception as e:
        return {"status": "error", "message": f"Trash failed: {e}"}


# ============================================================================
# Triage & summarize (LLM-powered)
# ============================================================================

def triage_inbox(max_results: int = 15) -> List[Dict[str, Any]]:
    """
    Fetch unread messages and classify each via local LLM.
    Categories: urgent, action-needed, informational, spam, newsletter
    """
    messages = fetch_messages(query="is:unread", max_results=max_results)
    if not messages:
        return []

    try:
        from daemon.llm import classify, is_available
        use_llm = is_available()
    except ImportError:
        use_llm = False

    categories = ["urgent", "action-needed", "informational", "spam", "newsletter"]

    triaged = []
    for msg in messages:
        text = f"From: {msg['from']}\nSubject: {msg['subject']}\n{msg['snippet']}"

        if use_llm:
            category = classify(text, categories)
        else:
            category = _rule_based_triage(msg)

        triaged.append({
            **msg,
            "category": category or "informational",
        })

    return triaged


def _rule_based_triage(msg: Dict[str, Any]) -> str:
    """Fallback triage when LLM is unavailable."""
    subject = (msg.get("subject") or "").lower()
    sender = (msg.get("from") or "").lower()
    snippet = (msg.get("snippet") or "").lower()

    if any(w in subject for w in ["urgent", "asap", "critical", "action required"]):
        return "urgent"
    if any(w in subject for w in ["unsubscribe", "newsletter", "digest", "weekly"]):
        return "newsletter"
    if any(w in sender for w in ["noreply", "no-reply", "notifications", "marketing"]):
        return "newsletter"
    if any(w in subject for w in ["please", "request", "invoice", "payment", "confirm"]):
        return "action-needed"
    return "informational"


def summarize_inbox(max_results: int = 10) -> str:
    """Fetch recent messages and produce a bullet-point summary."""
    messages = fetch_messages(max_results=max_results)
    if not messages:
        return "Inbox is empty."

    try:
        from daemon.llm import query as llm_query, is_available
        use_llm = is_available()
    except ImportError:
        use_llm = False

    if use_llm:
        lines = []
        for msg in messages:
            lines.append(f"- From: {msg['from']}, Subject: {msg['subject']}, Snippet: {msg['snippet'][:100]}")
        inbox_text = "\n".join(lines)

        prompt = (
            "Summarize these emails as bullet points. "
            "Group by urgency. Be concise (1 line per email).\n\n"
            f"{inbox_text[:2000]}"
        )
        summary = llm_query(prompt, max_tokens=512, temperature=0.3)
        if summary:
            return summary

    # Fallback: manual summary
    lines = [f"{len(messages)} recent messages:"]
    for msg in messages:
        unread = " [UNREAD]" if msg.get("is_unread") else ""
        lines.append(f"  {msg['from'][:30]}: {msg['subject'][:50]}{unread}")
    return "\n".join(lines)


# ============================================================================
# ChromaDB indexing & semantic search
# ============================================================================

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

_chroma_client = None
_collection = None


def _get_collection():
    """Lazy-init ChromaDB collection for Gmail messages."""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    if not CHROMA_AVAILABLE:
        return None

    GMAIL_DB_DIR.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(GMAIL_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    _collection = _chroma_client.get_or_create_collection(
        name="elara_gmail",
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def _message_doc_id(message_id: str) -> str:
    """Stable document ID for a Gmail message."""
    return hashlib.sha256(f"gmail:{message_id}".encode()).hexdigest()[:16]


def index_messages(messages: List[Dict[str, Any]]) -> int:
    """Index message summaries into ChromaDB. Returns count of new items."""
    collection = _get_collection()
    if collection is None:
        return 0

    indexed = 0
    for msg in messages:
        doc_id = _message_doc_id(msg["id"])

        # Skip duplicates
        try:
            existing = collection.get(ids=[doc_id])
            if existing and existing["ids"]:
                continue
        except Exception as e:
            logger.warning("Failed to check duplicate Gmail message %s: %s", msg.get("id", "?"), e)

        text = f"From: {msg.get('from', '')} Subject: {msg.get('subject', '')} {msg.get('snippet', '')}"
        now = datetime.now().isoformat()

        collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[{
                "gmail_id": msg["id"],
                "thread_id": msg.get("thread_id", ""),
                "from": msg.get("from", ""),
                "subject": msg.get("subject", ""),
                "date": msg.get("date", ""),
                "indexed_at": now,
            }],
        )
        indexed += 1

    return indexed


def search_messages(query: str, n: int = 10) -> List[Dict[str, Any]]:
    """Semantic search across indexed Gmail messages."""
    collection = _get_collection()
    if collection is None:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n, 50),
        )
    except Exception as e:
        logger.warning(f"Gmail search failed: {e}")
        return []

    items = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            score = 1.0 - dist

            items.append({
                "id": meta.get("gmail_id", doc_id),
                "thread_id": meta.get("thread_id", ""),
                "from": meta.get("from", ""),
                "subject": meta.get("subject", ""),
                "date": meta.get("date", ""),
                "score": round(score, 3),
            })

    return items


def sync(max_results: int = 50) -> Dict[str, Any]:
    """Fetch new messages since last sync and index them."""
    cache = load_validated(CACHE_FILE, GmailCache)

    # Fetch recent messages
    query = ""
    if cache.last_sync:
        # Gmail search supports after:YYYY/MM/DD
        try:
            dt = datetime.fromisoformat(cache.last_sync)
            query = f"after:{dt.strftime('%Y/%m/%d')}"
        except ValueError:
            pass

    messages = fetch_messages(query=query, max_results=max_results)
    if not messages:
        return {"status": "ok", "new_messages": 0, "total_indexed": cache.indexed_count}

    new_count = index_messages(messages)

    # Update cache
    cache.last_sync = datetime.now().isoformat()
    cache.indexed_count += new_count
    save_validated(CACHE_FILE, cache)

    return {
        "status": "ok",
        "fetched": len(messages),
        "new_indexed": new_count,
        "total_indexed": cache.indexed_count,
    }


def get_sync_stats() -> Dict[str, Any]:
    """Get sync state and indexed count."""
    cache = load_validated(CACHE_FILE, GmailCache)
    collection = _get_collection()
    db_count = collection.count() if collection else 0

    return {
        "authorized": is_authorized(),
        "last_sync": cache.last_sync,
        "indexed_count": db_count,
        "cache_indexed": cache.indexed_count,
    }
