from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    revision_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    @property
    def source_label(self) -> str:
        return f"[{self.chunk_id}] {self.doc_title} / {self.section} / {self.revision_date or 'дата не вказана'}"
