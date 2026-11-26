from __future__ import annotations

from app.search.models import Chunk


class ContextBuilder:
    def __init__(self, max_tokens: int = 1500):
        self.max_tokens = max_tokens

    def build(self, chunks: list[Chunk]) -> tuple[list[Chunk], list[str]]:
        selected: list[Chunk] = []
        used: list[str] = []
        budget_tokens = self.max_tokens

        for chunk in chunks:
            approx_tokens = max(1, len(chunk.text.split()) + 30)
            if approx_tokens <= budget_tokens:
                selected.append(chunk)
                used.append(chunk.chunk_id)
                budget_tokens -= approx_tokens
            else:
                break

        return selected, used

    def format_context(self, chunks: list[Chunk]) -> str:
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            lines.append(
                f"[#{idx}] {chunk.doc_title} | section: {chunk.section} | revision: {chunk.revision_date or 'n/a'}\n{chunk.text}"
            )
        return "\n\n".join(lines)
