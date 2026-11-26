from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.search.models import Chunk


class SearchIndex:
    _index_version = 2
    _max_chunk_chars = 1200
    _token_pattern = re.compile(r"[a-zа-яіїєґ0-9]+", re.IGNORECASE)
    _stop_words = {
        "а", "але", "без", "був", "була", "було", "бути", "ви", "від", "він",
        "вона", "вони", "для", "до", "же", "з", "за", "і", "із", "й", "на",
        "не", "чи", "що", "як", "я", "у", "та", "це", "цей", "ця", "ці",
        "про", "по", "під", "при", "є", "можна", "чи", "скільки", "який",
        "яка", "яке", "які", "коли", "де", "чи", "мені", "мій", "моє",
        "the", "a", "an", "and", "or", "is", "are", "to", "of", "for",
    }
    _word_endings = tuple(
        sorted(
            {
                "иями", "ями", "ами", "ого", "ему", "ому", "ими", "ими",
                "ій", "ий", "ій", "ою", "ею", "ого", "его", "ому", "ему",
                "ов", "ев", "ей", "ам", "ям", "ах", "ях", "ом", "ем",
                "ою", "ею", "ів", "їв", "и", "і", "а", "я", "у", "ю",
                "е", "є", "о", "ь", "й", "ы", "ов", "ей",
            },
            key=len,
            reverse=True,
        )
    )

    def __init__(self, docs_dir: str | Path | None = None):
        self.docs_dir = Path(docs_dir) if docs_dir else settings.docs_dir
        self.index_path = self.docs_dir / "index.json"
        self._chunks: list[Chunk] = []
        self.rebuild()

    def search(self, query: str, top_k: int = 5, threshold: float | None = None) -> list[Chunk]:
        if not self._chunks:
            return []

        threshold = threshold if threshold is not None else settings.similarity_threshold
        query_tokens = {
            self._stem(token)
            for token in self._token_pattern.findall(query.lower())
            if token not in self._stop_words
        }
        if not query_tokens:
            query_tokens = {
                self._stem(token) for token in self._token_pattern.findall(query.lower())
            }
        if not query_tokens:
            return []

        results: list[Chunk] = []

        for chunk in self._chunks:
            searchable = f"{chunk.doc_title} {chunk.section} {chunk.text}".lower()
            document_tokens = {
                self._stem(token) for token in self._token_pattern.findall(searchable)
            }
            matches = query_tokens & document_tokens
            title_tokens = {
                self._stem(token)
                for token in self._token_pattern.findall(
                    f"{chunk.doc_title} {chunk.section}".lower()
                )
            }
            score = (
                len(matches) + 0.5 * len(matches & title_tokens)
            ) / len(query_tokens)
            if score >= threshold:
                chunk.score = score
                results.append(chunk)

        return sorted(results, key=lambda c: c.score, reverse=True)[: top_k]

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    @classmethod
    def _stem(cls, token: str) -> str:
        for ending in cls._word_endings:
            if token.endswith(ending) and len(token) - len(ending) >= 3:
                return token[: -len(ending)]
        return token

    @staticmethod
    def _read_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None

        try:
            end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
        except StopIteration:
            return None

        metadata: dict[str, str] = {}
        for line in lines[1:end]:
            key, separator, value = line.partition(":")
            if separator:
                metadata[key.strip().lower()] = value.strip().strip("\"'")
        return metadata, "\n".join(lines[end + 1 :]).strip()

    @classmethod
    def _split_sections(cls, text: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        section_name = "Основне"
        paragraphs: list[str] = []
        current_lines: list[str] = []

        def append_paragraph() -> None:
            paragraph = "\n".join(current_lines).strip()
            if paragraph:
                paragraphs.append(paragraph)
            current_lines.clear()

        def append_chunks() -> None:
            append_paragraph()
            content = "\n\n".join(paragraphs).strip()
            if not content:
                paragraphs.clear()
                return

            parts: list[str] = []
            current = ""
            for paragraph in content.split("\n\n"):
                while len(paragraph) > cls._max_chunk_chars:
                    split_at = paragraph.rfind(" ", 0, cls._max_chunk_chars)
                    if split_at < 1:
                        split_at = cls._max_chunk_chars
                    parts.append(paragraph[:split_at].strip())
                    paragraph = paragraph[split_at:].strip()
                if current and len(current) + len(paragraph) + 2 > cls._max_chunk_chars:
                    parts.append(current)
                    current = paragraph
                else:
                    current = f"{current}\n\n{paragraph}".strip()
            if current:
                parts.append(current)
            sections.extend((section_name, part) for part in parts if part)
            paragraphs.clear()

        for line in text.splitlines():
            heading = re.match(r"^#{2,6}\s+(.+?)\s*#*\s*$", line)
            if heading:
                append_chunks()
                section_name = heading.group(1).strip()
            elif not line.strip():
                append_paragraph()
            else:
                current_lines.append(line)
        append_chunks()
        return sections

    def rebuild(self) -> None:
        if not self.docs_dir.exists():
            raise FileNotFoundError(f"Docs directory not found: {self.docs_dir}")

        chunk_list: list[Chunk] = []
        for file in sorted(self.docs_dir.glob("*.md")):
            text = file.read_text(encoding="utf-8")
            if file.name.lower() == "readme.md":
                continue
            parsed = self._read_frontmatter(text)
            if parsed is None:
                continue
            metadata, body = parsed
            if (
                metadata.get("audience", "").casefold() != "клієнти"
                or metadata.get("status", "").casefold() != "чинний"
                or metadata.get("category", "").casefold() in {"внутрішнє", "внутреннее"}
            ):
                continue

            doc_title = metadata.get("title") or file.stem
            for index, (section, content) in enumerate(self._split_sections(body), start=1):
                chunk_list.append(
                    Chunk(
                        chunk_id=f"{file.stem}-{index}",
                        doc_id=file.stem,
                        doc_title=doc_title,
                        section=section,
                        text=content,
                        revision_date=metadata.get("updated"),
                        metadata={
                            **metadata,
                            "source_file": file.name,
                            "internal": False,
                            "archived": False,
                        },
                    )
                )

        self._chunks = chunk_list
        serialized = {
            "version": self._index_version,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "doc_title": chunk.doc_title,
                    "section": chunk.section,
                    "text": chunk.text,
                    "revision_date": chunk.revision_date,
                    "metadata": chunk.metadata,
                    "score": chunk.score,
                }
                for chunk in chunk_list
            ],
        }
        self.index_path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8"
        )
