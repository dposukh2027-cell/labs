from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HistoryItem:
    role: str
    content: str


@dataclass
class MessageHistory:
    items: List[HistoryItem] = field(default_factory=list)

    def add(self, role: str, content: str) -> None:
        self.items.append(HistoryItem(role=role, content=content))

    def as_messages(self) -> List[dict]:
        return [{'role': item.role, 'content': item.content} for item in self.items]

    def trim_for_budget(self, budget_tokens: int, reserve_tokens: int = 300) -> None:
        if budget_tokens <= 0:
            self.items = []
            return

        max_items = max(1, min(len(self.items), 8))
        if len(self.items) <= max_items:
            return

        keep = [self.items[0]] + self.items[-(max_items - 1):]
        self.items = keep

    def keep_relevant_only(self, current_user_text: str) -> None:
        if not self.items:
            return
        filtered = []
        current = current_user_text.lower()
        keywords = {word for word in current.replace('-', ' ').split() if len(word) > 3}

        for item in self.items:
            text = item.content.lower()
            if item.role == 'user':
                if not keywords:
                    filtered.append(item)
                    continue
                if any(keyword in text for keyword in keywords) or 'order' in text:
                    filtered.append(item)
            else:
                filtered.append(item)

        self.items = filtered[-8:]
