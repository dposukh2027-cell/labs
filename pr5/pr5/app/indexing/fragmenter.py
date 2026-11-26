from __future__ import annotations

import re
from typing import Iterable


SECTION_PATTERN = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)


def split_into_sections(text: str) -> list[str]:
    lines = text.splitlines()
    chunks: list[str] = []
    current: list[str] = []

    for line in lines:
        if re.match(r"^#{1,6}\s+", line):
            if current:
                chunks.append("\n".join(current).strip())
                current = []
        current.append(line)

    if current:
        chunks.append("\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def split_into_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    if not text:
        return []

    raw = re.sub(r"\s+", " ", text).strip()
    if len(raw) <= chunk_size:
        return [raw]

    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(start + chunk_size, len(raw))
        chunk = raw[start:end]
        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)
        if end == len(raw):
            break
        start += max(1, chunk_size - overlap)
    return chunks


def build_fragments(doc_title: str, body: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    sections = split_into_sections(body)
    fragments: list[str] = []

    for section in sections:
        paragraph_fragments = chunk_text(section, chunk_size=chunk_size, overlap=overlap)
        for part in paragraph_fragments:
            fragments.append(f"Document: {doc_title}\n{part}")

    if not fragments:
        for part in chunk_text(body, chunk_size=chunk_size, overlap=overlap):
            fragments.append(f"Document: {doc_title}\n{part}")

    return fragments
