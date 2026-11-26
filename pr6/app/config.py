from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    max_context_tokens: int = int(os.getenv("MAX_CONTEXT_TOKENS", 1500))
    search_top_k: int = int(os.getenv("SEARCH_TOP_K", 8))
    model_context_limit: int = int(os.getenv("MODEL_CONTEXT_LIMIT", 5))
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", 0.15))
    app_title: str = os.getenv("APP_TITLE", "Сузір'я RAG помічник")
    app_env: str = os.getenv("APP_ENV", "development")

    @property
    def docs_dir(self) -> Path:
        return BASE_DIR / "docs"

    @property
    def eval_dir(self) -> Path:
        return BASE_DIR / "eval"


settings = Settings()
