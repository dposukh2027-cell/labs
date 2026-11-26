from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.config import APP_CONFIG
from app.indexing.fragmenter import build_fragments
from app.models.sentence_embedder import SentenceEmbedder
from app.services.metadata_parser import read_docs_folder


class KnowledgeIndex:
    def __init__(self, index_path: str | Path | None = None):
        self.index_path = Path(index_path or APP_CONFIG["index_path"])
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = SentenceEmbedder()
        self.model_name = self.embedder.model_name
        self.fragments: list[str] = []
        self.metadata: list[dict] = []
        self.vectors: np.ndarray | None = None

    def ingest(self, docs_dir: str | Path, chunk_size: int = 500, overlap: int = 100):
        fragments: list[str] = []
        metadata_list: list[dict] = []

        for doc_name, meta, body in read_docs_folder(docs_dir):
            title = meta.get("title", doc_name)
            for fragment in build_fragments(title, body, chunk_size=chunk_size, overlap=overlap):
                fragments.append(fragment)
                item = {
                    "document": doc_name,
                    "title": title,
                    "category": meta.get("category", "unknown"),
                    "product": meta.get("product", "unknown"),
                    "audience": meta.get("audience", "public"),
                    "status": meta.get("status", "active"),
                    "date": meta.get("date", ""),
                    "source": str(Path(docs_dir) / doc_name),
                }
                metadata_list.append(item)

        if not fragments:
            raise ValueError(f"No fragments found in {docs_dir}")

        vectors = self.embedder.encode(fragments, normalize=True)
        self.fragments = fragments
        self.metadata = metadata_list
        self.vectors = vectors

    def save(self, path: str | Path | None = None):
        write_path = Path(path or self.index_path)
        write_path.parent.mkdir(parents=True, exist_ok=True)

        np.savez_compressed(
            str(write_path),
            vectors=self.vectors.astype(np.float32),
            model_name=np.array([self.model_name], dtype=object),
        )

        payload = {
            "fragments": self.fragments,
            "metadata": self.metadata,
            "model_name": self.model_name,
        }
        with open(str(write_path.with_suffix(".json")), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load(self, path: str | Path | None = None):
        load_path = Path(path or self.index_path)
        if not load_path.exists():
            raise FileNotFoundError(f"Index not found at {load_path}")

        data = np.load(str(load_path))
        self.vectors = data["vectors"].astype(np.float32)
        self.model_name = str(data["model_name"][0])

        json_path = load_path.with_suffix(".json")
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        self.fragments = payload["fragments"]
        self.metadata = payload["metadata"]

    def similar(self, query: str, top_k: int = 5, threshold: float = 0.0, filters: dict | None = None):
        if self.vectors is None or self.fragments == []:
            raise ValueError("Index is empty. Build it first.")

        query_vector = self.embedder.encode_query(query)
        scores = self.vectors @ query_vector
        results = []

        for idx, score in enumerate(scores):
            if threshold and score < threshold:
                continue
            item = {"index": idx, "score": float(score), "fragment": self.fragments[idx], "metadata": self.metadata[idx]}
            if filters:
                ok = True
                for key, value in filters.items():
                    value = str(value).strip().lower()
                    if not value:
                        continue
                    actual = str(item["metadata"].get(key, "")).strip().lower()
                    if actual != value:
                        ok = False
                        break
                if not ok:
                    continue
            results.append(item)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
