from __future__ import annotations

import re
from typing import Iterable, List, Sequence


ORDER_PATTERN = re.compile(r'\bORD-\d{4}-\d{4}\b', re.IGNORECASE)


def extract_order_number(text: str) -> str | None:
    match = ORDER_PATTERN.search(text or '')
    return match.group(0).upper() if match else None


def trim_history_for_budget(history: Sequence[dict], budget_tokens: int, reserve_tokens: int = 300) -> list[dict]:
    if not history:
        return []

    if budget_tokens <= reserve_tokens:
        return history[:1]

    kept: list[dict] = []
    seen_order = False
    for item in history:
        content = str(item.get('content', ''))
        if extract_order_number(content):
            kept.append(item)
            seen_order = True

    if not kept:
        kept = [history[0]]

    for item in history:
        if item not in kept:
            if len(kept) >= 6:
                continue
            kept.append(item)

    ordered = [history[0]] + [item for item in history[1:-1] if item in kept and item is not history[0]] + [history[-1]]
    return ordered[:8]
