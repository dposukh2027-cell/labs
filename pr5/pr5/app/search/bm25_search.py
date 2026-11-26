from __future__ import annotations

import re
import time
from typing import Any

from rank_bm25 import BM25Okapi


def normalize_tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[\wа-щьюєїіґ’\-]+", text, flags=re.UNICODE)]


class BM25Search:
    def __init__(self, documents: list[str]):
        self.documents = documents
        self.tokens = [normalize_tokens(doc) for doc in documents]
        self.index = BM25Okapi(self.tokens)

    def search(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None, metadata: list[dict] | None = None):
        start = time.perf_counter()
        query_tokens = normalize_tokens(query)
        if not query_tokens:
            return [], 0.0
        scores = self.index.get_scores(query_tokens)

        ranked = []
        for idx, score in enumerate(scores):
            if filters and metadata:
                ok = True
                for key, value in filters.items():
                    if not value:
                        continue
                    actual = str(metadata[idx].get(key, "")).strip().lower()
                    if actual != str(value).strip().lower():
                        ok = False
                        break
                if not ok:
                    continue
            ranked.append({"index": idx, "score": float(score), "fragment": self.documents[idx], "metadata": metadata[idx] if metadata else {}})

        ranked.sort(key=lambda x: x["score"], reverse=True)
        elapsed = time.perf_counter() - start
        return ranked[:top_k], elapsed
