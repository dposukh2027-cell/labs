from __future__ import annotations

from app.search.models import Chunk


def filter_for_model(chunks: list[Chunk], *, max_items: int = 5, exclude_internal: bool = True, exclude_archived: bool = True) -> list[Chunk]:
    filtered: list[Chunk] = []
    for chunk in chunks:
        metadata = (chunk.metadata or {})

        if exclude_internal and (
            metadata.get("internal") is True
            or str(metadata.get("audience", "")).casefold() == "персонал"
            or str(metadata.get("category", "")).casefold() in {"внутрішнє", "внутреннее"}
        ):
            continue
        if exclude_archived and (
            metadata.get("archived") is True
            or str(metadata.get("status", "")).casefold() == "архів"
        ):
            continue

        filtered.append(chunk)

    return filtered[:max_items]
