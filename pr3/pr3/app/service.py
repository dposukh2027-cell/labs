from __future__ import annotations

from pathlib import Path

from app.config import settings


def load_context(path: Path | str | None = None) -> str:
    target = Path(path) if path else settings.context_path
    return target.read_text(encoding="utf-8")


def build_answer_payload(user_message: str, context_text: str, *, temperature: float | None = None, top_p: float | None = None, max_tokens: int | None = None) -> dict:
    return {
        "user_message": user_message,
        "context_text": context_text,
        "temperature": temperature if temperature is not None else settings.temperature,
        "top_p": top_p if top_p is not None else settings.top_p,
        "max_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
    }
