from __future__ import annotations

import asyncio
import time
from typing import Any

from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError

from app.config import settings


class LLMServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class LLMService:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.request_timeout,
        )

    def _build_messages(self, user_message: str, context_text: str) -> list[dict[str, str]]:
        system_prompt = (
            "Ти помічник служби підтримки інтернет-магазину. "
            "Відповідай лише на підставі наданих правил. "
            "Якщо в правилах інформації немає — прямо скажи, що її немає, і не вигадуй. "
            "Якщо питання можна зрозуміти по-різному — попроси уточнення. "
            "Відповідай українською мовою, зрозумілою для клієнта."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "user", "content": f"Додатковий контекст магазину:\n{context_text}"},
        ]

    async def generate(self, user_message: str, context_text: str, *, temperature: float | None = None, top_p: float | None = None, max_tokens: int | None = None) -> dict[str, Any]:
        if not settings.api_key:
            raise LLMServiceError("LLM API key is missing. Set LLM_API_KEY in .env file.", 500)

        messages = self._build_messages(user_message, context_text)
        payload = {
            "model": settings.model_name,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.temperature,
            "top_p": top_p if top_p is not None else settings.top_p,
            "max_tokens": max_tokens if max_tokens is not None else settings.max_tokens,
        }

        started = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, settings.max_retries + 1):
            try:
                response = self.client.chat.completions.create(**payload)
                elapsed = round(time.perf_counter() - started, 3)
                answer = response.choices[0].message.content.strip()
                model_name = getattr(response.model, "__str__", lambda: settings.model_name)()
                return {
                    "answer": answer or "Відповіді не було отримано.",
                    "model": model_name,
                    "elapsed_seconds": elapsed,
                    "attempts": attempt,
                }
            except APITimeoutError as exc:
                last_error = exc
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff * attempt)
                    continue
                raise LLMServiceError("Час очікування відповіді від моделі вичерпано. Спробуйте ще раз пізніше.", 504) from exc
            except RateLimitError as exc:
                last_error = exc
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff * attempt)
                    continue
                raise LLMServiceError("Перевищено ліміт запитів до API моделі. Зачекайте кілька хвилин і повторіть спробу.", 429) from exc
            except AuthenticationError as exc:
                raise LLMServiceError("Помилка автентифікації API ключа. Перевірте LLM_API_KEY.", 401) from exc
            except APIConnectionError as exc:
                last_error = exc
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff * attempt)
                    continue
                raise LLMServiceError("Модель тимчасово недоступна. Спробуйте пізніше.", 503) from exc
            except APIError as exc:
                last_error = exc
                if attempt < settings.max_retries:
                    await asyncio.sleep(settings.retry_backoff * attempt)
                    continue
                raise LLMServiceError(f"API повернуло помилку: {exc}", 502) from exc
            except Exception as exc:
                raise LLMServiceError(f"Неочікувана помилка LLM: {exc}", 500) from exc

        if last_error is not None:
            raise LLMServiceError(f"Не вдалося виконати запит до моделі: {last_error}", 500)
        raise LLMServiceError("Не вдалося виконати запит до моделі.", 500)
