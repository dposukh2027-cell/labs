from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import APP_CONFIG
from app.indexing.indexer import KnowledgeIndex
from app.search.bm25_search import BM25Search


def load_queries(path: str | Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    index = KnowledgeIndex(APP_CONFIG["index_path"])
    index.load(APP_CONFIG["index_path"])

    queries = load_queries(Path(__file__).resolve().parent / "queries.json")
    results = []

    for item in queries:
        query = item["query"]
        expected = item["expected_document"]
        filters = item.get("filters", {})

        start = time.perf_counter()
        semantic = index.similar(query, top_k=10, threshold=0.0, filters=filters)
        semantic_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        keyword_search = BM25Search(index.fragments)
        keyword_results, keyword_elapsed = keyword_search.search(query, top_k=10, filters=filters, metadata=index.metadata)
        keyword_elapsed = time.perf_counter() - start

        positions = []
        for candidate in semantic:
            positions.append(candidate["metadata"]["document"])
        semantic_rank = None
        for idx, doc in enumerate(positions, start=1):
            if doc == expected:
                semantic_rank = idx
                break

        keyword_positions = []
        for candidate in keyword_results:
            keyword_positions.append(candidate["metadata"].get("document"))
        keyword_rank = None
        for idx, doc in enumerate(keyword_positions, start=1):
            if doc == expected:
                keyword_rank = idx
                break

        results.append({
            "query": query,
            "expected_document": expected,
            "semantic_rank": semantic_rank,
            "keyword_rank": keyword_rank,
            "semantic_first_score": semantic[0]["score"] if semantic else None,
            "keyword_first_score": keyword_results[0]["score"] if keyword_results else None,
            "semantic_time_ms": round(semantic_elapsed * 1000, 3),
            "keyword_time_ms": round(keyword_elapsed * 1000, 3),
        })

    hit_1_semantic = sum(1 for row in results if row["semantic_rank"] == 1)
    hit_3_semantic = sum(1 for row in results if row["semantic_rank"] and row["semantic_rank"] <= 3)
    hit_1_keyword = sum(1 for row in results if row["keyword_rank"] == 1)
    hit_3_keyword = sum(1 for row in results if row["keyword_rank"] and row["keyword_rank"] <= 3)

    print(json.dumps({
        "semantic_hit@1": hit_1_semantic,
        "semantic_hit@3": hit_3_semantic,
        "keyword_hit@1": hit_1_keyword,
        "keyword_hit@3": hit_3_keyword,
        "rows": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
