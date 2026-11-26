"""Справжній провайдер: OpenAI-сумісний API — той самий, що в ПР3–ПР9."""

from typing import Any, Iterator

from openai import (APIConnectionError, APIStatusError, AuthenticationError, BadRequestError,
                    OpenAI, PermissionDeniedError, RateLimitError, Timeout)

from .base import Chunk, ProviderError, Request, Result


class OpenAICompatProvider:
    """Провайдер поверх OpenAI-сумісного API."""

    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("LLM_API_KEY is empty. Put the key in .env or set env LLM_API_KEY.")
        self.base_url = base_url
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.client = OpenAI(base_url=base_url, api_key=self.api_key, timeout=timeout)

    def _to_error(self, exc: Exception) -> ProviderError:
        if isinstance(exc, Timeout):
            return ProviderError("timeout", "Провайдер не відповів учасно", retryable=True, detail=str(exc))
        if isinstance(exc, RateLimitError):
            retry_after = getattr(exc, "response", None)
            retry_after_value = None
            if retry_after is not None:
                headers = getattr(retry_after, "headers", {}) or {}
                retry_after_value = headers.get("Retry-After")
                if retry_after_value is not None:
                    try:
                        retry_after_value = float(retry_after_value)
                    except (TypeError, ValueError):
                        retry_after_value = None
            return ProviderError("rate_limit", "Перевищено ліміт провайдера", retryable=True,
                                 retry_after=retry_after_value, detail=str(exc))
        if isinstance(exc, APIConnectionError):
            return ProviderError("unavailable", "Провайдер недоступний", retryable=True, detail=str(exc))
        if isinstance(exc, AuthenticationError):
            return ProviderError("auth", "Невірний або прострочений ключ доступу", retryable=False, detail=str(exc))
        if isinstance(exc, PermissionDeniedError):
            return ProviderError("auth", "Доступ до API заборонено: перевірте ключ, доступ до проекту й платіжні налаштування", retryable=False, detail=str(exc))
        if isinstance(exc, BadRequestError):
            return ProviderError("bad_request", "Провайдер не прийняв запит", retryable=False, detail=str(exc))
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            if status in (429,):
                return ProviderError("rate_limit", "Перевищено ліміт провайдера", retryable=True, detail=str(exc))
            if status in (401, 403):
                return ProviderError("auth", "Помилка доступу до моделі", retryable=False, detail=str(exc))
            if status in (400,):
                return ProviderError("bad_request", "Невірний запит для моделі", retryable=False, detail=str(exc))
            return ProviderError("unavailable", "Провайдер повернув HTTP-статус помилки", retryable=status in (500, 502, 503, 504), detail=str(exc))
        return ProviderError("unknown", "Невідомий збій провайдера", retryable=False, detail=str(exc))

    def complete(self, request: Request) -> Result:
        """Отримати відповідь цілком."""
        try:
            response = self.client.chat.completions.create(
                model=request.model or self.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
            )
            choice = response.choices[0]
            text = choice.message.content or ""
            usage = None
            if getattr(response, "usage", None):
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }
            return Result(
                text=text,
                provider=self.name,
                model=getattr(response, "model", request.model or self.model),
                usage=usage,
                finish_reason=getattr(choice, "finish_reason", None),
                elapsed=None,
            )
        except Exception as exc:  # pragma: no cover - wrapped into ProviderError
            raise self._to_error(exc) from exc

    def stream(self, request: Request) -> Iterator[Chunk]:
        """Віддавати фрагменти відповіді в міру надходження."""
        try:
            stream = self.client.chat.completions.create(
                model=request.model or self.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            for event in stream:
                if not getattr(event, "choices", None):
                    continue
                choice = event.choices[0]
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None) or ""
                if isinstance(content, str):
                    chunk_text = content
                else:
                    chunk_text = "".join(part for part in content if isinstance(part, str))
                finish_reason = getattr(choice, "finish_reason", None)
                usage = None
                if getattr(event, "usage", None):
                    usage = {
                        "prompt_tokens": getattr(event.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(event.usage, "completion_tokens", 0),
                        "total_tokens": getattr(event.usage, "total_tokens", 0),
                    }
                yield Chunk(text=chunk_text, usage=usage, finish_reason=finish_reason)
        except Exception as exc:  # pragma: no cover - wrapped into ProviderError
            raise self._to_error(exc) from exc
