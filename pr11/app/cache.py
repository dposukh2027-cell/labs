"""Persistent, bounded TTL response cache."""

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from .providers.base import Request, Result

load_dotenv()

ENABLED = os.getenv("CACHE_ENABLED", "1") == "1"
TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "3600"))
MAX_ENTRIES = int(os.getenv("CACHE_MAX_ENTRIES", "500"))
CACHE_FILE = os.getenv("CACHE_FILE", "state/cache.json")
_lock = threading.RLock()
_entries: dict[str, dict] = {}
_hits = 0
_misses = 0
_bypassed = 0


def settings() -> dict:
    return {"enabled": ENABLED, "ttl_seconds": TTL_SECONDS, "max_entries": MAX_ENTRIES,
            "file": CACHE_FILE or None}


def _read() -> None:
    if not CACHE_FILE:
        return
    path = Path(CACHE_FILE)
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid cache file: {path}")
    _entries.update({key: value for key, value in payload.items() if isinstance(value, dict)})


def _save() -> None:
    if not CACHE_FILE:
        return
    path = Path(CACHE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_entries, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def make_key(request: Request, prompt_version: str) -> str:
    payload = {
        "provider": os.getenv("LLM_PROVIDER", "mock"),
        "model": request.model or os.getenv("LLM_MODEL", "mock-1"),
        "prompt_version": prompt_version,
        "messages": request.messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get(key: str) -> Result | None:
    global _hits, _misses, _bypassed
    if not ENABLED:
        return None
    now = time.time()
    with _lock:
        _read()
        item = _entries.get(key)
        if item is None:
            _misses += 1
            return None
        if now - float(item["saved_at"]) > TTL_SECONDS:
            del _entries[key]
            _save()
            _misses += 1
            return None
        _hits += 1
        result = Result(**item["result"])
        result.cached = True
        return result


def bypassed() -> None:
    global _bypassed
    with _lock:
        _bypassed += 1


def put(key: str, result: Result) -> None:
    if not ENABLED or MAX_ENTRIES <= 0 or result.finish_reason not in (None, "stop"):
        return
    stored = {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "usage": result.usage,
        "finish_reason": result.finish_reason,
        "elapsed": result.elapsed,
        "cost": result.cost,
        "cost_estimated": result.cost_estimated,
        "cached": False,
    }
    with _lock:
        _read()
        _entries[key] = {"saved_at": time.time(), "result": stored}
        cutoff = time.time() - TTL_SECONDS
        expired = [entry_key for entry_key, item in _entries.items()
                   if float(item.get("saved_at", 0)) < cutoff]
        for entry_key in expired:
            _entries.pop(entry_key, None)
        while len(_entries) > MAX_ENTRIES:
            oldest = min(_entries, key=lambda entry_key: _entries[entry_key].get("saved_at", 0))
            del _entries[oldest]
        _save()


def stats() -> dict:
    with _lock:
        _read()
        return {"hits": _hits, "misses": _misses, "bypassed": _bypassed, "entries": len(_entries)}
