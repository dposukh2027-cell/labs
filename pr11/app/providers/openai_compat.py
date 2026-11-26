"""Adapter for OpenAI-compatible chat-completions APIs."""

from typing import Iterator

from .base import Chunk, ProviderError, Request, Result


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is required for LLM_PROVIDER=openai") from exc
        self.model = model
        self.timeout = timeout
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    @staticmethod
    def _plain(value):
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value

    @staticmethod
    def _provider_error(exc: Exception) -> ProviderError:
        try:
            from openai import (
                APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError,
                InternalServerError, RateLimitError,
            )
        except ImportError:
            return ProviderError("unknown", "Помилка мовного провайдера.", detail=type(exc).__name__)

        if isinstance(exc, APITimeoutError):
            return ProviderError("timeout", "Провайдер не відповів вчасно.", retryable=True,
                                 detail=type(exc).__name__)
        if isinstance(exc, RateLimitError):
            response = getattr(exc, "response", None)
            retry_after = None
            if response is not None:
                try:
                    retry_after = float(response.headers.get("retry-after"))
                except (TypeError, ValueError):
                    pass
            return ProviderError("rate_limit", "Провайдер тимчасово обмежив запити.",
                                 retryable=True, retry_after=retry_after, detail=type(exc).__name__)
        if isinstance(exc, (APIConnectionError, InternalServerError)):
            return ProviderError("unavailable", "Провайдер тимчасово недоступний.",
                                 retryable=True, detail=type(exc).__name__)
        if isinstance(exc, AuthenticationError):
            return ProviderError("auth", "Не вдалося пройти автентифікацію у провайдера.",
                                 detail=type(exc).__name__)
        if isinstance(exc, BadRequestError):
            return ProviderError("bad_request", "Провайдер не прийняв запит.",
                                 detail=type(exc).__name__)
        return ProviderError("unknown", "Неочікувана помилка мовного провайдера.",
                             detail=type(exc).__name__)

    def _create(self, request: Request, *, stream: bool):
        try:
            return self.client.with_options(timeout=self.timeout).chat.completions.create(
                model=request.model or self.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=stream,
                **({"stream_options": {"include_usage": True}} if stream else {}),
            )
        except Exception as exc:
            raise self._provider_error(exc) from exc

    def complete(self, request: Request) -> Result:
        response = self._create(request, stream=False)
        try:
            choice = response.choices[0]
            return Result(text=choice.message.content or "", provider=self.name,
                          model=response.model or request.model or self.model,
                          usage=self._plain(response.usage), finish_reason=choice.finish_reason)
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderError("unknown", "Провайдер повернув некоректну відповідь.",
                                detail=type(exc).__name__) from exc

    def stream(self, request: Request) -> Iterator[Chunk]:
        response = self._create(request, stream=True)
        try:
            for item in response:
                usage = self._plain(getattr(item, "usage", None))
                choices = getattr(item, "choices", None) or []
                if not choices:
                    if usage is not None:
                        yield Chunk("", usage=usage)
                    continue
                choice = choices[0]
                text = getattr(choice.delta, "content", None) or ""
                yield Chunk(text, usage=usage, finish_reason=getattr(choice, "finish_reason", None))
        except ProviderError:
            raise
        except Exception as exc:
            raise self._provider_error(exc) from exc
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
