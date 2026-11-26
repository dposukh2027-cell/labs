"""Single path to providers: concurrency, retries, cache, budget and telemetry."""

import logging
import os
import queue
import random
import threading
import time
from dataclasses import replace
from typing import Callable, Iterator

from dotenv import load_dotenv

from . import budget, cache, costs, telemetry
from .providers.base import Chunk, Provider, ProviderError, Request, Result
from .providers.mock import MockProvider

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "mock")
FALLBACK = os.getenv("LLM_FALLBACK", "none")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
IDLE_TIMEOUT = float(os.getenv("LLM_IDLE_TIMEOUT", "8"))
TOTAL_TIMEOUT = float(os.getenv("LLM_TOTAL_TIMEOUT", "45"))
MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "3"))
BACKOFF_BASE = float(os.getenv("LLM_BACKOFF_BASE", "0.5"))
BACKOFF_MAX = float(os.getenv("LLM_BACKOFF_MAX", "8"))
MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "2")))
MODEL = os.getenv("LLM_MODEL") or None
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "600"))
_semaphore = threading.BoundedSemaphore(max(1, MAX_CONCURRENT))
_log = logging.getLogger("app.gateway")


class _ErrorProvider:
    def __init__(self, name: str, model: str, error: ProviderError) -> None:
        self.name = name
        self.model = model
        self.error = error

    def complete(self, request: Request) -> Result:
        raise self.error

    def stream(self, request: Request) -> Iterator[Chunk]:
        raise self.error


def settings() -> dict:
    return {
        "provider": PROVIDER, "fallback": FALLBACK, "model": MODEL,
        "timeout": TIMEOUT, "idle_timeout": IDLE_TIMEOUT,
        "total_timeout": TOTAL_TIMEOUT, "max_attempts": MAX_ATTEMPTS,
        "max_concurrent": MAX_CONCURRENT,
    }


def make_provider(name: str) -> Provider:
    if name == "mock":
        return MockProvider()
    from .providers.openai_compat import OpenAICompatProvider

    base_url = os.getenv("LLM_BASE_URL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    model = MODEL if name == "openai" else name
    if not base_url or not api_key or not model:
        return _ErrorProvider(
            name, model or "unknown",
            ProviderError("auth", "Налаштуйте LLM_BASE_URL, LLM_API_KEY і LLM_MODEL у .env."),
        )
    try:
        provider = OpenAICompatProvider(base_url, api_key, model, TIMEOUT)
    except RuntimeError as exc:
        return _ErrorProvider(
            name, model,
            ProviderError("unavailable", "Встановіть пакет openai для цього провайдера.",
                          detail=type(exc).__name__),
        )
    if name != "openai":
        provider.name = name
    return provider


def _identity(request: Request) -> dict:
    metadata = request.metadata
    return {
        "request_id": metadata.get("http_request_id") or telemetry.request_id_var.get(),
        "draft_id": metadata.get("draft_id"),
        "sample_id": metadata.get("request_id"),
        "client": metadata.get("client_id"),
        "prompt_version": metadata.get("prompt_version"),
    }


def _expected_cost(request: Request, provider_name: str) -> float | None:
    text = " ".join(str(message.get("content", "")) for message in request.messages)
    usage = {
        "prompt_tokens": max(1, (len(text) + 2) // 3),
        "completion_tokens": request.max_tokens,
    }
    value, _ = costs.estimate(usage, provider=provider_name, model=request.model)
    return value


def _stream_attempt(provider: Provider, request: Request, on_delta: Callable[[str], None],
                    is_cancelled: Callable[[], bool], deadline: float) -> tuple[str, dict | None, str | None, float | None]:
    messages: queue.Queue = queue.Queue(maxsize=8)
    stopped = threading.Event()
    started = time.monotonic()
    first_token = None

    def produce() -> None:
        try:
            for chunk in provider.stream(request):
                while not stopped.is_set():
                    try:
                        messages.put(("chunk", chunk), timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if stopped.is_set():
                    return
            while not stopped.is_set():
                try:
                    messages.put(("done", None), timeout=0.1)
                    break
                except queue.Full:
                    continue
        except Exception as exc:
            try:
                messages.put(("error", exc), timeout=0.1)
            except queue.Full:
                pass

    worker = threading.Thread(target=produce, daemon=True)
    worker.start()
    parts: list[str] = []
    usage = None
    finish_reason = None
    try:
        while True:
            if is_cancelled():
                raise ProviderError("cancelled", "Генерацію скасовано.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("timeout", "Вичерпано загальний час очікування.", retryable=True)
            try:
                kind, value = messages.get(timeout=min(IDLE_TIMEOUT, remaining))
            except queue.Empty as exc:
                raise ProviderError("timeout", "Провайдер надто довго не надсилав фрагменти.",
                                    retryable=True) from exc
            if kind == "done":
                break
            if kind == "error":
                error = value
                if isinstance(error, ProviderError):
                    raise error
                raise ProviderError("unknown", "Помилка потоку провайдера.",
                                    detail=type(error).__name__) from error
            chunk = value
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.text:
                if first_token is None:
                    first_token = time.monotonic() - started
                parts.append(chunk.text)
                on_delta(chunk.text)
    finally:
        stopped.set()
    return "".join(parts), usage, finish_reason, first_token


def generate(request: Request, on_delta: Callable[[str], None],
             on_status: Callable[[dict], None], is_cancelled: Callable[[], bool]) -> Result:
    started = time.monotonic()
    deadline = started + TOTAL_TIMEOUT
    identity = _identity(request)
    key = cache.make_key(request, str(request.metadata.get("prompt_version", "")))
    fresh = bool(request.metadata.get("fresh"))

    cached = None
    if not cache.ENABLED:
        _log.info("llm.cache_disabled", extra={**identity, "cache_key": key, "cached": False})
    elif fresh:
        cache.bypassed()
        _log.info("llm.cache_bypassed", extra={**identity, "cache_key": key, "cached": False})
    else:
        cached = cache.get(key)
        if cached is None:
            _log.info("llm.cache_miss", extra={**identity, "cache_key": key, "cached": False})
    if cached is not None:
        for field in (cached.text[index:index + 120] for index in range(0, len(cached.text), 120)):
            on_delta(field)
        avoided_cost = cached.cost or 0.0
        cached.cost = 0.0
        cached.cost_estimated = False
        cached.usage = None
        cached.elapsed = time.monotonic() - started
        request.metadata["attempts"] = 0
        request.metadata["fallback"] = False
        request.metadata["first_token_seconds"] = cached.elapsed
        _log.info("llm.cache_hit", extra={**identity, "cache_key": key, "cached": True,
                                         "provider": cached.provider, "model": cached.model,
                                         "cost": 0.0, "avoided_cost": avoided_cost})
        on_status({"provider": cached.provider, "model": cached.model, "cached": True})
        return cached

    acquired = False
    while not acquired and time.monotonic() < deadline:
        if is_cancelled():
            raise ProviderError("cancelled", "Генерацію скасовано.")
        acquired = _semaphore.acquire(timeout=min(0.1, max(0.0, deadline - time.monotonic())))
    if not acquired:
        raise ProviderError("timeout", "Перевищено час очікування в черзі.", retryable=True)

    queue_wait = time.monotonic() - started
    names = [PROVIDER]
    if FALLBACK != "none" and FALLBACK != PROVIDER:
        names.append(FALLBACK)
    attempts_total = 0
    last_error: ProviderError | None = None
    fallback_used = False
    total_spent = 0.0
    estimated_spend = False
    total_usage: dict | None = None
    final_result: Result | None = None
    first_token_total = None
    last_provider: str | None = None
    partial_output = False
    try:
        for provider_index, provider_name in enumerate(names):
            fallback_used = provider_index > 0
            if fallback_used:
                on_status({"fallback": True, "provider": provider_name})
            retry_limit = MAX_ATTEMPTS if provider_index == 0 else 1
            for local_attempt in range(1, retry_limit + 1):
                if is_cancelled():
                    raise ProviderError("cancelled", "Генерацію скасовано.")
                if time.monotonic() >= deadline:
                    last_error = ProviderError("timeout", "Вичерпано загальний час очікування.")
                    break

                attempts_total += 1
                provider = make_provider(provider_name)
                last_provider = provider.name
                attempt_started = time.monotonic()
                prompt_text = " ".join(str(message.get("content", "")) for message in request.messages)
                attempt_text = ""
                attempt_parts: list[str] = []
                attempt_emitted = False

                def send_delta(text: str) -> None:
                    nonlocal attempt_emitted
                    attempt_parts.append(text)
                    attempt_emitted = attempt_emitted or bool(text)
                    on_delta(text)

                usage = None
                finish_reason = None
                first_token = None
                attempt_cost = 0.0
                estimated = True
                call_completed = False
                cost_recorded = False
                error = None
                budget_resets_at = None
                try:
                    _log.info("llm.attempt.start", extra={
                        **identity, "attempt": attempts_total, "provider": provider.name,
                        "model": request.model or getattr(provider, "model", None),
                        "queue_wait_ms": round(queue_wait * 1000, 1),
                        "cache_key": key, "fallback": fallback_used,
                    })
                    on_status({"attempt": attempts_total, "provider": provider.name,
                               "fallback": fallback_used})
                    budget.check(_expected_cost(request, provider.name))
                    provider_request = replace(request, model=getattr(provider, "model", request.model))
                    attempt_text, usage, finish_reason, first_token = _stream_attempt(
                        provider, provider_request, send_delta, is_cancelled,
                        min(deadline, attempt_started + TIMEOUT))
                    call_completed = True
                    actual_cost, estimated = costs.estimate(
                        usage, provider=provider.name, model=getattr(provider, "model", None),
                        text=prompt_text + attempt_text,
                    )
                    attempt_cost = actual_cost or 0.0
                    budget.record(actual_cost)
                    cost_recorded = True
                    total_spent += attempt_cost
                    if usage is not None:
                        total_usage = usage
                    final_result = Result(
                        text=attempt_text, provider=provider.name,
                        model=getattr(provider, "model", request.model or "unknown"),
                        usage=usage, finish_reason=finish_reason,
                        elapsed=time.monotonic() - attempt_started,
                        cost=actual_cost, cost_estimated=estimated,
                    )
                    budget_state = budget.status()
                    if budget_state["warning"]:
                        _log.warning("budget.warning", extra={**identity, **budget_state})
                    _log.info("llm.attempt", extra={
                        **identity, "attempt": attempts_total, "provider": provider.name,
                        "model": final_result.model, "duration_ms": round(final_result.elapsed * 1000, 1),
                        "queue_wait_ms": round(queue_wait * 1000, 1),
                        "first_token_ms": round(first_token * 1000, 1) if first_token is not None else None,
                        "status": "ok", "kind": None, "tokens_in": (usage or {}).get("prompt_tokens"),
                        "tokens_out": (usage or {}).get("completion_tokens"), "usage": usage,
                        "cost": actual_cost, "cost_estimated": estimated,
                        "cache_key": key, "cached": False, "fallback": fallback_used,
                    })
                    first_token_total = first_token
                    break
                except budget.BudgetExceeded as exc:
                    budget_resets_at = exc.resets_at
                    error = ProviderError("budget", str(exc), retryable=False,
                                          detail=type(exc).__name__)
                except ProviderError as exc:
                    error = exc
                    attempt_text = "".join(attempt_parts)
                except Exception as exc:
                    if call_completed and cost_recorded and final_result is not None:
                        first_token_total = first_token
                        _log.error("llm.attempt.telemetry_error", extra={
                            **identity, "attempt": attempts_total, "provider": provider.name,
                            "model": getattr(provider, "model", None),
                            "error_type": type(exc).__name__, "status": "ok",
                            "cost": attempt_cost, "cache_key": key, "fallback": fallback_used,
                        })
                        break
                    error = ProviderError("unknown", "Неочікувана помилка шлюзу.",
                                          detail=type(exc).__name__)

                if error is not None:
                    if (not cost_recorded and not isinstance(provider, _ErrorProvider) and
                            error.kind not in {"budget", "auth", "bad_request"}):
                        actual_cost, estimated = costs.estimate(
                            usage, provider=provider.name, model=getattr(provider, "model", None),
                            text=prompt_text + attempt_text,
                        )
                        attempt_cost = actual_cost or 0.0
                        budget.record(actual_cost)
                        cost_recorded = True
                        total_spent += attempt_cost
                        estimated_spend = estimated_spend or estimated
                        if usage is not None:
                            total_usage = usage
                        budget_state = budget.status()
                        if budget_state["warning"]:
                            _log.warning("budget.warning", extra={**identity, **budget_state})
                    elif error.kind == "budget" or isinstance(provider, _ErrorProvider):
                        budget.release()
                        estimated = False
                    elif error.kind in {"auth", "bad_request"}:
                        budget.release()
                        estimated = False
                    partial_output = partial_output or attempt_emitted
                    can_retry = (
                        error.retryable and local_attempt < retry_limit and
                        not is_cancelled() and time.monotonic() < deadline and
                        not attempt_emitted and not attempt_text
                    )
                    _log.log(logging.WARNING if can_retry or fallback_used else logging.ERROR,
                             "llm.attempt", extra={
                                 **identity, "attempt": attempts_total, "provider": provider.name,
                                 "model": getattr(provider, "model", None),
                                 "duration_ms": round((time.monotonic() - attempt_started) * 1000, 1),
                                 "queue_wait_ms": round(queue_wait * 1000, 1),
                                 "first_token_ms": round(first_token * 1000, 1) if first_token is not None else None,
                                 "status": "failed", "kind": error.kind,
                                 "error_type": error.detail, "resets_at": budget_resets_at,
                                 "tokens_in": (usage or {}).get("prompt_tokens"),
                                 "tokens_out": (usage or {}).get("completion_tokens"),
                                 "usage": usage, "cost": attempt_cost,
                                 "cost_estimated": estimated,
                                 "cache_key": key, "cached": False, "fallback": fallback_used,
                                 "will_retry": can_retry,
                             })
                    last_error = error
                    if can_retry:
                        delay = min(BACKOFF_MAX, error.retry_after if error.retry_after is not None
                                    else BACKOFF_BASE * (2 ** (local_attempt - 1)))
                        if error.retry_after is None:
                            delay *= random.uniform(0.8, 1.2)
                        if time.monotonic() + delay >= deadline:
                            break
                        sleep_until = time.monotonic() + max(0.0, delay)
                        while time.monotonic() < sleep_until:
                            if is_cancelled():
                                last_error = ProviderError("cancelled", "Генерацію скасовано.")
                                break
                            remaining = sleep_until - time.monotonic()
                            if remaining > 0:
                                time.sleep(min(0.05, remaining))
                        if last_error is not None and last_error.kind == "cancelled":
                            break
                        continue
                    break
            if final_result is not None:
                break
            if partial_output:
                break
            if last_error and last_error.kind in {"budget", "cancelled"}:
                break

        if final_result is None:
            if last_error is None:
                last_error = ProviderError("unknown", "Не вдалося отримати відповідь від провайдера.")
            _log.error("llm.failed", extra={
                **identity, "attempts": attempts_total, "provider": last_provider or names[0],
                "status": "failed", "kind": last_error.kind, "cost": total_spent,
                "fallback": fallback_used, "cache_key": key,
            })
            raise last_error

        final_result.elapsed = time.monotonic() - started
        final_result.cost = round(total_spent, 9)
        final_result.cost_estimated = final_result.cost_estimated or estimated_spend
        final_result.usage = total_usage if total_usage is not None else final_result.usage
        request.metadata["attempts"] = attempts_total
        request.metadata["fallback"] = fallback_used
        request.metadata["first_token_seconds"] = first_token_total
        cache.put(key, final_result)
        _log.info("llm.done", extra={
            **identity, "attempts": attempts_total, "provider": final_result.provider,
            "model": final_result.model, "duration_ms": round(final_result.elapsed * 1000, 1),
            "first_token_ms": round(first_token_total * 1000, 1) if first_token_total is not None else None,
            "status": "ok", "usage": final_result.usage, "cost": final_result.cost,
            "cost_estimated": final_result.cost_estimated, "cached": False,
            "fallback": fallback_used, "cache_key": key,
        })
        return final_result
    finally:
        _semaphore.release()
