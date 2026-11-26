"""Local provider for demonstrations and tests; it never uses network or API keys."""

import math
import os
import random
import time
from typing import Iterator

from dotenv import load_dotenv

from .base import Chunk, ProviderError, Request, Result
from .. import samples

load_dotenv()

FIRST_DELAY_MS = int(os.getenv("MOCK_FIRST_DELAY_MS", "600"))
DELAY_MS = int(os.getenv("MOCK_DELAY_MS", "40"))
FAILURE_RATE = float(os.getenv("MOCK_FAILURE_RATE", "0"))
FAILURE_KIND = os.getenv("MOCK_FAILURE_KIND", "unavailable")


class MockProvider:
    name = "mock"
    model = "mock-1"

    def _failure(self, request: Request) -> str | None:
        forced = request.metadata.get("mock_failure_kind")
        if forced:
            return str(forced)
        if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
            return FAILURE_KIND
        return None

    @staticmethod
    def _usage(request: Request, text: str) -> dict:
        prompt_chars = sum(len(str(message.get("content", ""))) for message in request.messages)
        prompt_tokens = max(1, math.ceil(prompt_chars / 3))
        completion_tokens = max(1, math.ceil(len(text) / 3))
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _reply(self, request: Request) -> str:
        request_id = str(request.metadata.get("request_id", ""))
        sample = samples.get(request_id)
        if sample is None:
            raise ProviderError("bad_request", "Невідоме тестове звернення.", retryable=False)
        return str(sample.get("reply_example") or "")

    def complete(self, request: Request) -> Result:
        text = "".join(chunk.text for chunk in self.stream(request))
        return Result(text=text, provider=self.name, model=self.model,
                      usage=self._usage(request, text), finish_reason="stop")

    def stream(self, request: Request) -> Iterator[Chunk]:
        failure = self._failure(request)
        if failure and failure != "mid_stream":
            if failure == "rate_limit":
                raise ProviderError(failure, "Демо-провайдер тимчасово обмежив запити.",
                                    retryable=True, retry_after=0.1)
            retryable = failure in {"timeout", "unavailable"}
            raise ProviderError(failure, "Демо-збій підставного провайдера.",
                                retryable=retryable)

        text = self._reply(request)
        pieces = [text[index:index + 36] for index in range(0, len(text), 36)]
        for index, piece in enumerate(pieces):
            time.sleep((FIRST_DELAY_MS if index == 0 else DELAY_MS) / 1000)
            if failure == "mid_stream" and index == 2:
                raise ProviderError("unavailable", "Демо-потік обірвався посеред відповіді.",
                                    retryable=True)
            yield Chunk(piece)
        yield Chunk("", usage=self._usage(request, text), finish_reason="stop")
