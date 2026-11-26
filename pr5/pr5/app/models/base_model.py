from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseEmbedder(ABC):
    @abstractmethod
    def encode(self, texts: list[str], normalize: bool = True) -> Any:
        raise NotImplementedError

    @abstractmethod
    def encode_query(self, text: str) -> Any:
        raise NotImplementedError
