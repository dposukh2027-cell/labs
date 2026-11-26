from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("LLM_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    model_name: str = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    top_p: float = float(os.getenv("LLM_TOP_P", "0.9"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "250"))
    request_timeout: int = int(os.getenv("LLM_REQUEST_TIMEOUT", "30"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    retry_backoff: float = float(os.getenv("LLM_RETRY_BACKOFF", "1.5"))
    context_path: Path = BASE_DIR / "context.md"


settings = Settings()
