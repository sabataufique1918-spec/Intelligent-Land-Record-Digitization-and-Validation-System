"""Local AI: a vision-language model running in Ollama on this computer (AI_PROVIDER=ollama).

Takes the same content blocks, JSON schema and system prompt as the Claude path in ai_extraction.py,
so everything downstream (field cleaning, confidence scoring) works unchanged. Nothing is sent over
the internet. Small local models are much less accurate than Claude, especially on handwriting, and
slow on a small GPU; every value still goes through officer review.

Setup: install Ollama (https://ollama.com), then `ollama pull <OLLAMA_MODEL>`.
"""

import json
import urllib.error
import urllib.request

from ..config import OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL

# Enough room for page images (~1-2k tokens each at 1280 px), the prompt and the JSON answer.
CONTEXT_TOKENS = 8192
# Longest answer allowed. Small models sometimes repeat themselves until they run out of room; this
# stops them early instead of at the timeout. A page's fields plus a transcription fit well within it.
MAX_ANSWER_TOKENS = 3000


class LocalAIError(Exception):
    pass


def _post(path: str, body: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_URL}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def status() -> dict:
    """{"running": bool, "model_installed": bool, "message": str | None}"""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            models = {m["name"] for m in json.loads(response.read()).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return {"running": False, "model_installed": False,
                "message": "Ollama is not running. Start the Ollama app (or run `ollama serve`)."}
    installed = OLLAMA_MODEL in models or f"{OLLAMA_MODEL}:latest" in models
    return {"running": True, "model_installed": installed,
            "message": None if installed else f"The model is not downloaded yet. Run: ollama pull {OLLAMA_MODEL}"}


def request(content: list, schema: dict, system: str) -> dict:
    """Run one extraction. content: Anthropic-style blocks (base64 images + text). Returns {"model", "fields"}."""
    images = [b["source"]["data"] for b in content if b["type"] == "image"]
    text = "\n\n".join(b["text"] for b in content if b["type"] == "text")
    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text, **({"images": images} if images else {})},
        ],
        "format": schema,  # Ollama constrains the output to this JSON schema
        "stream": False,
        "think": False,  # answer directly; thinking makes small models several times slower
        "keep_alive": "15m",  # keep the model loaded between documents
        "options": {"temperature": 0, "num_ctx": CONTEXT_TOKENS, "num_predict": MAX_ANSWER_TOKENS},
    }
    try:
        response = _post("/api/chat", body, OLLAMA_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code == 404:
            raise LocalAIError(f"The local model '{OLLAMA_MODEL}' is not downloaded. Run: ollama pull {OLLAMA_MODEL}") from exc
        raise LocalAIError(f"The local AI (Ollama) returned an error ({exc.code}): {detail}") from exc
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise LocalAIError(f"The local AI took longer than {OLLAMA_TIMEOUT_SECONDS:.0f} s and was stopped.") from exc
        raise LocalAIError("Could not reach the local AI. Is Ollama running?") from exc

    if response.get("done_reason") == "length":
        raise LocalAIError("The local AI's answer ran too long and was stopped (it may have started "
                           "repeating itself). Enter the details by hand.")
    try:
        data = json.loads(response["message"]["content"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise LocalAIError("The local AI did not return valid JSON.") from exc
    return {"model": f"{response.get('model', OLLAMA_MODEL)} (local)", "fields": data}
