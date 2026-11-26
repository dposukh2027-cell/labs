"""Підставний провайдер: поводиться як справжній, але без мережі й
ключа — і збоїть тоді, коли ви просите."""

import os
import random
import time
from typing import Iterator

from dotenv import load_dotenv

from app.samples import get as sample_get
from .base import Chunk, ProviderError, Request, Result

load_dotenv()

FIRST_DELAY_MS = int(os.getenv("MOCK_FIRST_DELAY_MS", "600"))
DELAY_MS = int(os.getenv("MOCK_DELAY_MS", "40"))
FAILURE_RATE = float(os.getenv("MOCK_FAILURE_RATE", "0"))
FAILURE_KIND = os.getenv("MOCK_FAILURE_KIND", "unavailable")


class MockProvider:
    """Провайдер без моделі: канонічні тексти, затримки, збої на вимогу."""

    name = "mock"
    model = "mock-1"

    def _text_for(self, request: Request) -> str:
        sample = sample_get(request.metadata.get("request_id", ""))
        if sample and sample.get("reply_example"):
            return sample["reply_example"]
        request_text = " ".join(m.get("content", "") for m in request.messages if isinstance(m, dict))
        return request_text or "Тестова відповідь від підставного провайдера."

    def _failure_kind_for(self, request: Request) -> str | None:
        override = request.metadata.get("failure_kind")
        if override:
            return str(override)
        rate = float(request.metadata.get("failure_rate", FAILURE_RATE))
        if rate <= 0:
            return None
        if request.metadata.get("deterministic_failure") is not None:
            return str(request.metadata["deterministic_failure"])
        if random.random() < rate:
            return str(request.metadata.get("forced_kind", FAILURE_KIND))
        return None

    def complete(self, request: Request) -> Result:
        chunks = list(self.stream(request))
        text = "".join(chunk.text for chunk in chunks)
        return Result(text=text, provider=self.name, model=self.model, usage={"prompt_tokens": 0, "completion_tokens": 0}, finish_reason="stop", elapsed=None, attempts=1)

    def stream(self, request: Request) -> Iterator[Chunk]:
        text = self._text_for(request)
        kind = self._failure_kind_for(request)
        if kind == "rate_limit":
            raise ProviderError("rate_limit", "Підставний провайдер відповів 429", retryable=True, retry_after=2.0)
        if kind == "auth":
            raise ProviderError("auth", "Помилка доступу до підставного провайдера", retryable=False)
        if kind == "unavailable":
            raise ProviderError("unavailable", "Підставний провайдер недоступний", retryable=True)
        if kind == "timeout":
            time.sleep(max((FIRST_DELAY_MS + 1500) / 1000.0, 1.5))
            return
        parts = [text[i:i + 80] for i in range(0, len(text), 80)]
        if kind == "mid_stream":
            for idx, part in enumerate(parts[:3]):
                time.sleep((FIRST_DELAY_MS if idx == 0 else DELAY_MS) / 1000.0)
                yield Chunk(text=part)
            raise ProviderError("unavailable", "Підставний провайдер обірвав потік", retryable=True)

        for idx, part in enumerate(parts):
            time.sleep((FIRST_DELAY_MS if idx == 0 else DELAY_MS) / 1000.0)
            yield Chunk(text=part)
        yield Chunk(text="", finish_reason="stop", usage={"prompt_tokens": 0, "completion_tokens": 0})
