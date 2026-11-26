from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv('OPENAI_API_KEY', '')
    base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    model: str = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    token_budget: int = int(os.getenv('TOKEN_BUDGET', '1200'))
    history_limit: int = int(os.getenv('SESSION_HISTORY_LIMIT', '8'))
    max_retries: int = 2


settings = Settings()
