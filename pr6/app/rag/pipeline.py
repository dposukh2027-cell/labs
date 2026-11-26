from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.llm.client import LLMClient
from app.rag.schema import LLMAnswer
from app.rag.validator import AnswerValidator
from app.search.filters import filter_for_model
from app.search.indexer import SearchIndex
from app.search.models import Chunk


class RAGPipeline:
    def __init__(self, index: SearchIndex | None = None, llm_client: LLMClient | None = None):
        self.index = index or SearchIndex()
        self.llm_client = llm_client or LLMClient()
        self.validator = AnswerValidator()

    def ask(self, question: str) -> dict[str, Any]:
        if not question or not question.strip():
            raise ValueError("Question must not be empty")

        search_start = time.time()
        raw_hits = self.index.search(question, top_k=settings.search_top_k, threshold=settings.similarity_threshold)
        filtered_hits = filter_for_model(raw_hits, max_items=settings.model_context_limit)
        search_ms = round((time.time() - search_start) * 1000, 2)

        if not filtered_hits:
            return {
                "answer_text": "У базі знань немає достатньо інформації для відповіді на це питання.",
                "source_refs": [],
                "found": False,
                "sources_seen_by_model": [],
                "search_ms": search_ms,
                "generation_ms": 0.0,
                "usage": {},
                "search_hits": [chunk.chunk_id for chunk in raw_hits],
                "context": [],
            }

        generation_start = time.time()
        context = "\n\n".join(
            f"[{idx}] {chunk.doc_title} | section: {chunk.section} | revision: {chunk.revision_date or 'n/a'}\n{chunk.text}"
            for idx, chunk in enumerate(filtered_hits, start=1)
        )
        prompt = (
            "Ти помічник, який відповідає лише на основі наданих документів. "
            "Якщо в документах немає відповіді — скажи прямо, що інформації немає. "
            "Не вигадуй і не використовуй знання поза контекстом. "
            "Поверни JSON з ключами answer (рядок), sources (масив рядків із номерами джерел, наприклад "
            '["1", "2"]) і found (boolean). У sources вказуй лише номери реально наданих джерел. '
            "Якщо відповіді немає в контексті, встанови found=false і sources=[]; "
            "не цитуй джерела, які не підтверджують відповідь. "
            "Питання клієнта: " + question + "\n\nКонтекст:\n" + context
        )

        llm_response = self.llm_client.generate(prompt)
        generation_ms = round((time.time() - generation_start) * 1000, 2)

        answer_model = LLMAnswer.model_validate(llm_response)
        available_refs = [str(index) for index in range(1, len(filtered_hits) + 1)]
        valid, validation_errors = self.validator.validate(answer_model, available_refs)

        if not valid:
            answer_model.answer = "Відповідь не пройшла перевірку якості. Для безпечної відповіді використовую відмову."
            answer_model.found = False
            answer_model.sources = []
            validation_errors = validation_errors

        result = {
            "answer_text": answer_model.answer,
            "source_refs": answer_model.sources,
            "found": bool(answer_model.found),
            "sources_seen_by_model": [chunk.chunk_id for chunk in filtered_hits],
            "search_ms": search_ms,
            "generation_ms": generation_ms,
            "usage": llm_response.get("usage", {}),
            "search_hits": [chunk.chunk_id for chunk in raw_hits],
            "context": [
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_title": chunk.doc_title,
                    "section": chunk.section,
                    "revision_date": chunk.revision_date,
                    "text": chunk.text,
                }
                for chunk in filtered_hits
            ],
            "validation_errors": validation_errors,
        }
        return result
