"""Local LLM (Ollama) tools — status, direct query, triage."""

import json
from elara_mcp._app import mcp
from daemon import llm


@mcp.tool()
def elara_llm(
    action: str = "status",
    prompt: str = "",
    text: str = "",
    categories: str = "",
) -> str:
    """
    Local LLM interface via Ollama (mistral:7b).

    Args:
        action: What to do:
            "status"    — Check if Ollama is running, list models
            "query"     — Send a direct prompt (needs prompt)
            "classify"  — Classify text into categories (needs text + categories)
            "summarize" — Summarize text in 2 sentences (needs text)
            "triage"    — Assess conversation importance (needs text)

    Returns:
        Result from local LLM, or status info
    """
    if action == "status":
        info = llm.status()
        return json.dumps(info, indent=2)

    if action == "query":
        if not prompt:
            return "Error: 'prompt' required for query action"
        result = llm.query(prompt)
        if result is None:
            return "Ollama unavailable — is it running? (`ollama serve`)"
        return result

    if action == "classify":
        if not text or not categories:
            return "Error: 'text' and 'categories' (comma-separated) required"
        cats = [c.strip() for c in categories.split(",")]
        result = llm.classify(text, cats)
        if result is None:
            return "Ollama unavailable"
        return result

    if action == "summarize":
        if not text:
            return "Error: 'text' required for summarize action"
        result = llm.summarize(text)
        if result is None:
            return "Ollama unavailable"
        return result

    if action == "triage":
        if not text:
            return "Error: 'text' required for triage action"
        # Split on a delimiter or use full text as user side
        parts = text.split("\n---\n", 1)
        user_text = parts[0]
        assistant_text = parts[1] if len(parts) > 1 else ""
        result = llm.triage_memory(user_text, assistant_text)
        if result is None:
            return "Ollama unavailable"
        return json.dumps(result, indent=2)

    return f"Unknown action: {action}. Use: status, query, classify, summarize, triage"
