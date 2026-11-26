from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceRef:
    ref_id: str
    doc_title: str
    section: str
    revision_date: str | None
    snippet: str


@dataclass
class RAGResponse:
    answer_text: str
    source_refs: list[str] = field(default_factory=list)
    found: bool = True
    raw_response: dict[str, Any] | None = None
    used_context: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
