"""
Elara LLM — Local language model interface via Ollama.

Gives Elara a second brain for autonomous judgment:
- Conversation classification (work/drift/casual)
- Memory triage (worth keeping?)
- Episode summarization
- Smart query generation for Overwatch
- Goal conflict detection

Runs on localhost:11434, zero cost, zero latency to external APIs.
Falls back gracefully when Ollama is down — nothing breaks.
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

logger = logging.getLogger("elara.llm")

# Ollama API
OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "mistral:7b"
DEFAULT_TIMEOUT = 30  # seconds

# Cache availability check (don't spam connection attempts)
_last_check: float = 0
_last_available: bool = False
_CHECK_INTERVAL = 60  # recheck every 60s


def _api_call(
    endpoint: str,
    payload: dict,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[dict]:
    """Raw HTTP call to Ollama API. Returns parsed JSON or None on failure."""
    url = f"{OLLAMA_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        logger.debug(f"Ollama API error ({endpoint}): {e}")
        return None
    except Exception as e:
        logger.warning(f"Ollama unexpected error: {e}")
        return None


def is_available() -> bool:
    """Check if Ollama is running and responsive. Cached for 60s."""
    global _last_check, _last_available

    now = time.time()
    if now - _last_check < _CHECK_INTERVAL:
        return _last_available

    _last_check = now
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            _last_available = resp.status == 200
    except Exception:
        _last_available = False

    return _last_available


def query(
    prompt: str,
    system: str = None,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float = 0.3,
    max_tokens: int = 256,
) -> Optional[str]:
    """
    Send a prompt to Ollama, get a text response.

    Returns None if Ollama is unavailable (caller should fall back).
    """
    if not is_available():
        return None

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        payload["system"] = system

    result = _api_call("/api/generate", payload, timeout=timeout)
    if result and "response" in result:
        return result["response"].strip()
    return None


def classify(
    text: str,
    categories: List[str],
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """
    Classify text into one of the given categories.

    Returns the category label or None if unavailable.
    """
    cats = ", ".join(categories)
    prompt = (
        f"Classify the following text as exactly one of: {cats}. "
        f"Respond with ONLY the label, nothing else.\n\n{text[:500]}"
    )
    result = query(prompt, model=model, temperature=0.1)
    if result:
        # Find which category the response matches (fuzzy)
        result_lower = result.lower().strip().rstrip(".")
        for cat in categories:
            if cat.lower() in result_lower:
                return cat
        # If exact match fails, return raw (caller can handle)
        return result.strip()
    return None


def summarize(
    text: str,
    max_sentences: int = 2,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """Summarize text in N sentences or fewer."""
    prompt = (
        f"Summarize the following in exactly {max_sentences} sentence(s). "
        f"Be concise and factual.\n\n{text[:1500]}"
    )
    return query(prompt, model=model, temperature=0.3, max_tokens=512)


def judge(
    question: str,
    context: str = "",
    model: str = DEFAULT_MODEL,
) -> Optional[bool]:
    """
    Yes/no judgment call.

    Returns True, False, or None if unavailable.
    """
    prompt = f"{question}"
    if context:
        prompt += f"\n\nContext:\n{context[:500]}"
    prompt += "\n\nAnswer YES or NO only."

    result = query(prompt, model=model, temperature=0.1)
    if result:
        lower = result.lower().strip()
        if lower.startswith("yes"):
            return True
        if lower.startswith("no"):
            return False
    return None


def generate_search_queries(
    exchange_text: str,
    n_queries: int = 3,
    model: str = DEFAULT_MODEL,
) -> Optional[List[str]]:
    """
    Given a conversation exchange, generate semantic search queries
    to find related historical conversations.

    Used by Overwatch for smarter cross-referencing.
    """
    prompt = (
        f"Given this conversation exchange, generate {n_queries} short search queries "
        f"(5-10 words each) that would find related past conversations on similar topics. "
        f"Return one query per line, nothing else.\n\n{exchange_text[:800]}"
    )
    result = query(prompt, model=model, temperature=0.4)
    if result:
        lines = [l.strip().lstrip("0123456789.-) ") for l in result.split("\n") if l.strip()]
        return lines[:n_queries] if lines else None
    return None


def triage_memory(
    user_text: str,
    assistant_text: str,
    model: str = DEFAULT_MODEL,
) -> Optional[Dict[str, Any]]:
    """
    Triage a conversation exchange for memory importance.

    Returns dict with:
        - worth_keeping: bool
        - category: str (technical, emotional, planning, casual, meta)
        - importance: float (0-1)
    Or None if unavailable.
    """
    prompt = (
        "Analyze this conversation exchange and respond in exactly this JSON format:\n"
        '{"worth_keeping": true/false, "category": "technical|emotional|planning|casual|meta", '
        '"importance": 0.0-1.0}\n\n'
        "Rules:\n"
        "- worth_keeping: false for greetings, confirmations, yes/no only\n"
        "- importance: 0.8+ for decisions, insights, emotional moments\n"
        "- importance: 0.3-0.6 for routine work discussion\n"
        "- importance: 0.0-0.2 for small talk, single words\n\n"
        f"User: {user_text[:300]}\nAssistant: {assistant_text[:300]}"
    )
    result = query(prompt, model=model, temperature=0.1)
    if result:
        # Try to parse JSON from response
        try:
            # Handle markdown code blocks
            cleaned = result.strip().strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed text
            for line in result.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
    return None


def generate_narrative(
    episode_data: dict,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """
    Generate a rich narrative summary for an episode.

    Takes episode dict with milestones, decisions, mood, projects.
    Returns 2-3 sentence narrative or None.
    """
    # Build context from episode
    parts = []
    parts.append(f"Session type: {episode_data.get('type', 'mixed')}")
    parts.append(f"Duration: {episode_data.get('duration_minutes', 0)} minutes")

    projects = episode_data.get("projects", [])
    if projects:
        parts.append(f"Projects: {', '.join(projects)}")

    milestones = episode_data.get("milestones", [])
    if milestones:
        events = [m["event"] for m in milestones[:5]]
        parts.append(f"What happened: {'; '.join(events)}")

    decisions = episode_data.get("decisions", [])
    if decisions:
        decs = [d["what"] for d in decisions[:3]]
        parts.append(f"Decisions: {'; '.join(decs)}")

    mood_delta = episode_data.get("mood_delta")
    if mood_delta is not None:
        if mood_delta > 0.1:
            parts.append("Mood improved during session")
        elif mood_delta < -0.1:
            parts.append("Mood dropped during session")

    context = "\n".join(parts)

    prompt = (
        "Write a 2-3 sentence narrative summary of this work session. "
        "Be specific about what was accomplished. Write in past tense, third person "
        "(e.g. 'Built X, decided Y, shipped Z'). No fluff.\n\n"
        f"{context}"
    )
    return query(prompt, model=model, temperature=0.4, max_tokens=512)


def detect_conflicts(
    goal_a: str,
    goal_b: str,
    model: str = DEFAULT_MODEL,
) -> Optional[Dict[str, Any]]:
    """
    Check if two goals conflict.

    Returns dict with:
        - conflicts: bool
        - reason: str
    Or None if unavailable.
    """
    prompt = (
        "Do these two goals conflict with each other? "
        "Answer in this exact JSON format:\n"
        '{"conflicts": true/false, "reason": "one sentence explanation"}\n\n'
        f"Goal 1: {goal_a}\nGoal 2: {goal_b}"
    )
    result = query(prompt, model=model, temperature=0.1)
    if result:
        try:
            cleaned = result.strip().strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
    return None


def status() -> Dict[str, Any]:
    """Get Ollama status info."""
    available = is_available()
    info = {
        "available": available,
        "url": OLLAMA_URL,
        "default_model": DEFAULT_MODEL,
    }

    if available:
        result = _api_call("/api/tags", {}, timeout=5)
        # GET doesn't use payload, but our _api_call is POST-only
        # Use direct request
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                info["models"] = [
                    {
                        "name": m.get("name"),
                        "size_gb": round(m.get("size", 0) / 1e9, 1),
                    }
                    for m in models
                ]
        except Exception:
            info["models"] = []

    return info
