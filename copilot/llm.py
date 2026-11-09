"""Cached, deterministic LLM calls. temperature 0, JSON output, cache/llm/<sha256>.json."""
import hashlib
import json
import os
import re
import threading
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CACHE = ROOT / "cache" / "llm"
CACHE.mkdir(parents=True, exist_ok=True)

MODEL_FAST = os.getenv("MODEL_FAST", "claude-haiku-5-5")
MODEL_DRAFT = os.getenv("MODEL_DRAFT", "claude-sonnet-5-5")

STATS = {"api_calls": 0, "cache_hits": 0}
_lock = threading.Lock()
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=6)
    return _client


def _thinking_off(model: str) -> dict:
    """Default thinking eats max_tokens and returns empty text. Haiku accepts 'disabled';
    Sonnet 5.5 requires 'between_tools' (no thinking before responding)."""
    return {"type": "disabled"} if "haiku" in model else {"type": "between_tools"}


def parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def call_json(model: str, system: str, prompt: str, max_tokens: int = 700) -> dict:
    key = hashlib.sha256(json.dumps([model, system, prompt]).encode("utf-8")).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        with _lock:
            STATS["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))["parsed"]
    client = _get_client()
    parsed, text = None, ""
    for attempt in range(2):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking=_thinking_off(model),
            # NOTE: current API rejects `temperature` ("Extra inputs are not permitted").
            # Determinism is guaranteed by this response cache: re-runs make zero API calls.
            system=system + "\n\nRespond with a single JSON object only. No prose, no code fences.",
            messages=[{"role": "user", "content": prompt + ("\n\nReturn ONLY valid JSON." if attempt else "")}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        with _lock:
            STATS["api_calls"] += 1
        try:
            parsed = parse_json(text)
            break
        except Exception:
            continue
    if parsed is None:
        parsed = {"_parse_error": True}
    path.write_text(json.dumps({"model": model, "raw": text, "parsed": parsed}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return parsed
