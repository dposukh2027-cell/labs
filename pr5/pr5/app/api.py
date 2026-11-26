from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import APP_CONFIG
from app.indexing.indexer import KnowledgeIndex
from app.search.bm25_search import BM25Search

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="Semantic Search for Suzirya Knowledge Base")
    index = KnowledgeIndex(APP_CONFIG["index_path"])
    index_loaded = False

    if APP_CONFIG["index_path"].exists():
        try:
            index.load(APP_CONFIG["index_path"])
            index_loaded = True
        except Exception:
            index_loaded = False

    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "index_ready": index_loaded,
                "model_name": index.model_name if index_loaded else APP_CONFIG["model_name"],
            },
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "index_ready": index_loaded,
            "model": index.model_name if index_loaded else APP_CONFIG["model_name"],
        }

    @app.post("/search")
    async def search(
        query: str = Form(""),
        top_k: int = Form(APP_CONFIG["top_k"]),
        threshold: float = Form(APP_CONFIG["similarity_threshold"]),
        category: str = Form(""),
        product: str = Form(""),
        audience: str = Form(""),
        status: str = Form(""),
    ):
        if not query.strip():
            raise HTTPException(status_code=400, detail="Порожній запит. Введіть текст для пошуку.")

        if not index_loaded:
            raise HTTPException(
                status_code=503,
                detail="Індекс не знайдено. Запустіть python scripts/build_index.py для побудови бази знань.",
            )

        filters = {
            "category": category.strip(),
            "product": product.strip(),
            "audience": audience.strip(),
            "status": status.strip(),
        }
        filters = {k: v for k, v in filters.items() if v}

        semantic_start = time.perf_counter()
        try:
            semantic = index.similar(query, top_k=top_k, threshold=threshold, filters=filters)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        semantic_elapsed = time.perf_counter() - semantic_start

        bm25 = BM25Search(index.fragments)
        keyword_start = time.perf_counter()
        keyword_results, keyword_time = bm25.search(query, top_k=top_k, filters=filters, metadata=index.metadata)
        keyword_elapsed = time.perf_counter() - keyword_start

        return {
            "semantic": [
                {
                    "score": item["score"],
                    "document": item["metadata"]["document"],
                    "title": item["metadata"]["title"],
                    "source": item["metadata"]["source"],
                    "metadata": item["metadata"],
                    "fragment": item["fragment"],
                }
                for item in semantic
            ],
            "keywords": [
                {
                    "score": item["score"],
                    "document": item["metadata"].get("document"),
                    "title": item["metadata"].get("title"),
                    "source": item["metadata"].get("source"),
                    "metadata": item["metadata"],
                    "fragment": item["fragment"],
                }
                for item in keyword_results
            ],
            "semantic_time_ms": round(semantic_elapsed * 1000, 3),
            "keyword_time_ms": round(keyword_elapsed * 1000, 3),
        }

    return app
