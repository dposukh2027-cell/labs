from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

print("BASE_DIR:", BASE_DIR)
print("API_KEY_SET:", bool(os.getenv("OPENAI_API_KEY")))
print("BASE_URL:", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
print("MODEL:", os.getenv("MODEL_NAME", "gpt-4o-mini"))
print("DOCS_EXISTS:", (BASE_DIR / "docs").exists())
