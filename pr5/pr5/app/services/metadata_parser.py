from __future__ import annotations

import re
from pathlib import Path


META_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_document_metadata(text: str) -> dict[str, str]:
    match = META_PATTERN.match(text)
    if not match:
        return {}

    block = match.group(1)
    metadata: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip()
    return metadata


def get_document_body(text: str) -> str:
    match = META_PATTERN.match(text)
    if not match:
        return text
    return text[match.end() :]


def read_docs_folder(docs_dir: str | Path):
    docs_dir = Path(docs_dir)
    for path in sorted(docs_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        metadata = parse_document_metadata(content)
        body = get_document_body(content)
        yield path.name, metadata, body
