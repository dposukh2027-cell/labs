from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = Path(os.getenv("DOCS_DIR", "docs")).resolve() if Path(os.getenv("DOCS_DIR", "docs")).is_absolute() else (BASE_DIR / os.getenv("DOCS_DIR", "docs")).resolve()

APP_CONFIG: dict[str, Any] = {
    "model_name": os.getenv("MODEL_NAME", "intfloat/multilingual-e5-small"),
    "index_path": (BASE_DIR / os.getenv("INDEX_PATH", "data/index.npz")).resolve(),
    "docs_dir": DOCS_DIR,
    "top_k": int(os.getenv("TOP_K", "5")),
    "similarity_threshold": float(os.getenv("SIMILARITY_THRESHOLD", "0.25")),
    "host": os.getenv("HOST", "0.0.0.0"),
    "port": int(os.getenv("PORT", "8000")),
}
