from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import APP_CONFIG
from app.indexing.indexer import KnowledgeIndex


def main():
    docs_dir = APP_CONFIG["docs_dir"]
    index_path = APP_CONFIG["index_path"]
    print(f"Reading docs from: {docs_dir}")
    index = KnowledgeIndex(index_path)
    index.ingest(docs_dir, chunk_size=500, overlap=100)
    index.save(index_path)
    print(f"Saved index to {index_path}")
    print(f"Fragments: {len(index.fragments)}")
    print(f"Model: {index.model_name}")


if __name__ == "__main__":
    main()
