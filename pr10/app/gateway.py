"""Шлюз до моделі: єдиний шлях, яким застосунок звертається до
провайдера.

Решта застосунку не викликає провайдерів напряму. Вона каже шлюзу
«згенеруй» — і отримує або результат, або контрольовану помилку. Між
цими двома подіями шлюз робить те, що не повинен робити ані провайдер,
ані веб-рівень, ані фонова задача:

* обирає провайдера за конфігурацією (`LLM_PROVIDER`) і запасний
  варіант (`LLM_FALLBACK`);
* тримає таймаути: на спробу, на бездіяльність у streaming, на весь
  запит разом зі спробами;
* повторює спроби — лише ті збої, які має сенс повторювати, з
  наростаючою паузою й випадковою часткою, не більше `MAX_ATTEMPTS`
  і не довше за `TOTAL_TIMEOUT`;
* обмежує кількість одночасних звертань до провайдера на весь
  застосунок (`MAX_CONCURRENT`);
* перериває роботу, коли той, хто просив, передумав;
* повідомляє, що відбувається: яка спроба, який провайдер, чи це
  запасний варіант — щоб сторінка могла це показати.

Шлюз не знає, що саме генерується (чернетка відповіді чи щось інше) і
звідки прийшов запит (сторінка, тест, скрипт). Він знає лише
`providers.base`.

Функції нижче — заготовки. Рішення з розділу 2 практичної роботи:

* три таймаути — на спробу, на бездіяльність, на весь запит. Який
  ловить що, і що стається, коли спливає кожен із них посеред
  streaming, коли частину тексту вже віддано;
* які `kind` повторювати, а які ні; що робити з `retry_after` від
  провайдера, якщо він більший за ваш бюджет часу;
* чи повторювати спробу після того, як перший фрагмент уже віддано
  споживачеві. Якщо так — як сказати йому «починаємо спочатку»;
* коли вмикати запасний варіант: після всіх спроб, після першої, одразу
  на певних видах збою? Що з результату має сказати, що він запасний;
* що означає `MAX_CONCURRENT`, коли місця немає: чекати (скільки?) чи
  відмовляти одразу — і як це відрізняється від обмеження частоти для
  клієнтів у `app/limits.py`;
* як передавати фрагменти й стан назовні: зворотний виклик, генератор,
  черга? Як дізнаватися про скасування між фрагментами й між спробами;
* що потрапляє в підсумок для журналу: спроби, провайдер, модель, час
  до першого фрагмента, загальний час, токени.
"""

import os
import random
import threading
import time
from typing import Callable

from dotenv import load_dotenv

from .providers.base import Provider, ProviderError, Request, Result
from .providers.mock import MockProvider
from .providers.openai_compat import OpenAICompatProvider

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai")
FALLBACK = os.getenv("LLM_FALLBACK", "none")

TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
IDLE_TIMEOUT = float(os.getenv("LLM_IDLE_TIMEOUT", "8"))
TOTAL_TIMEOUT = float(os.getenv("LLM_TOTAL_TIMEOUT", "45"))
MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "3"))
BACKOFF_BASE = float(os.getenv("LLM_BACKOFF_BASE", "0.5"))
BACKOFF_MAX = float(os.getenv("LLM_BACKOFF_MAX", "8"))
MAX_CONCURRENT = int(os.getenv("LLM_MAX_CONCURRENT", "2"))

MODEL = os.getenv("LLM_MODEL")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "600"))

_concurrency = threading.Semaphore(MAX_CONCURRENT)


def settings() -> dict:
    """Чинні налаштування шлюзу — для сторінки й журналу."""
    return {
        "provider": PROVIDER,
        "fallback": FALLBACK,
        "model": MODEL,
        "timeout": TIMEOUT,
        "idle_timeout": IDLE_TIMEOUT,
        "total_timeout": TOTAL_TIMEOUT,
        "max_attempts": MAX_ATTEMPTS,
        "max_concurrent": MAX_CONCURRENT,
    }


def make_provider(name: str) -> Provider:
    """Зібрати провайдера за назвою."""
    name = (name or "").strip().lower()
    if name in {"", "openai"}:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("auth", "Ключ API не задано. Скопіюйте його в .env або в env LLM_API_KEY.", retryable=False)
        return OpenAICompatProvider(
            base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            api_key=api_key,
            model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            timeout=TIMEOUT,
        )
    if name == "mock":
        return MockProvider()
    # Підтримка варіантів, коли запасний провайдер — це та сама адреса й ключ,
    # але інша модель; для цього інша назва моделі розглядається як ім'я провайдера.
    if name not in {"none"}:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("auth", "Ключ API не задано. Скопіюйте його в .env або в env LLM_API_KEY.", retryable=False)
        return OpenAICompatProvider(
            base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            api_key=api_key,
            model=name,
            timeout=TIMEOUT,
        )
    raise ValueError("provider 'none' не може бути створений")


def _sleep_backoff(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return max(float(retry_after), 0.0)
    delay = BACKOFF_BASE * (2 ** max(attempt - 1, 0))
    return min(delay + random.random() * BACKOFF_BASE, BACKOFF_MAX)


def _run_single_provider(provider: Provider, request: Request,
                        on_delta: Callable[[str], None],
                        on_status: Callable[[dict], None],
                        is_cancelled: Callable[[], bool],
                        attempt_number: int, fallback: bool) -> Result:
    text_parts: list[str] = []
    usage = None
    deadline = time.monotonic() + TIMEOUT
    stream = iter(provider.stream(request))
    last_activity = time.monotonic()
    try:
        on_status({"attempt": attempt_number, "provider": provider.name, "fallback": fallback, "status": "running"})
        while True:
            if is_cancelled():
                raise ProviderError("cancelled", "Генерацію скасовано", retryable=False)
            if time.monotonic() > deadline:
                raise ProviderError("timeout", "Таймаут спроби перевищено", retryable=True)
            if time.monotonic() - last_activity > IDLE_TIMEOUT:
                raise ProviderError("timeout", "Таймаут бездіяльності в потоці", retryable=True)
            try:
                chunk = next(stream)
            except StopIteration:
                break
            except Exception as exc:
                if isinstance(exc, ProviderError):
                    raise
                raise ProviderError("unknown", "Провайдер завершився з помилкою", retryable=True, detail=str(exc)) from exc
            last_activity = time.monotonic()
            if chunk.text:
                text_parts.append(chunk.text)
                on_delta(chunk.text)
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.finish_reason is not None:
                break
        result_text = "".join(text_parts)
        return Result(
            text=result_text,
            provider=provider.name,
            model=getattr(provider, "model", request.model or "unknown"),
            usage=usage,
            finish_reason="stop",
            elapsed=None,
            attempts=attempt_number,
        )
    except Exception as exc:  # pragma: no cover - defensive wrap
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("unknown", "Невідомий збій провайдера", retryable=False, detail=str(exc)) from exc


def generate(request: Request, on_delta: Callable[[str], None],
             on_status: Callable[[dict], None], is_cancelled: Callable[[], bool]) -> Result:
    """Згенерувати відповідь, дотримуючись таймаутів, спроб, обмеження
    одночасності й запасного варіанту."""
    total_started = time.monotonic()
    providers: list[Provider] = [make_provider(PROVIDER)]
    if FALLBACK and FALLBACK != "none" and FALLBACK.lower() != PROVIDER.lower():
        providers.append(make_provider(FALLBACK))

    last_error: ProviderError | None = None
    provider_index = 0
    attempt_number = 0
    while provider_index < len(providers):
        if is_cancelled():
            raise ProviderError("cancelled", "Генерацію скасовано", retryable=False)
        provider = providers[provider_index]
        while attempt_number < MAX_ATTEMPTS:
            attempt_number += 1
            if time.monotonic() - total_started >= TOTAL_TIMEOUT:
                raise ProviderError("unavailable", "Вичерпано загальний бюджет часу на запит", retryable=True)
            if not _concurrency.acquire(timeout=max(0.1, TOTAL_TIMEOUT - (time.monotonic() - total_started))):
                raise ProviderError("unavailable", "Занадто багато одночасних звернень до провайдера", retryable=True)
            try:
                if is_cancelled():
                    raise ProviderError("cancelled", "Генерацію скасовано", retryable=False)
                result = _run_single_provider(provider, request, on_delta, on_status, is_cancelled, attempt_number, provider_index > 0)
                return result
            except ProviderError as exc:
                last_error = exc
                if exc.kind == "cancelled":
                    raise
                if exc.retryable and attempt_number < MAX_ATTEMPTS and (time.monotonic() - total_started) < TOTAL_TIMEOUT:
                    wait_for = _sleep_backoff(attempt_number, exc.retry_after)
                    on_status({
                        "attempt": attempt_number,
                        "provider": provider.name,
                        "fallback": provider_index > 0,
                        "retry_in": round(wait_for, 2),
                        "status": "retry",
                    })
                    time.sleep(min(wait_for, max(0.0, TOTAL_TIMEOUT - (time.monotonic() - total_started))))
                    continue
                break
            finally:
                _concurrency.release()
        provider_index += 1
        attempt_number = 0

    if last_error is not None:
        raise last_error
    raise ProviderError("unknown", "Під час генерації не вдалося зібрати результат", retryable=False)
