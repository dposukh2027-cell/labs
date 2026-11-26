"""Фонове виконання чернеток і журнал подій для SSE-клієнтів.

Реєстр чернеток живе в памʼяті процесу. Для кожної роботи створюється
потік; події містять кореляційні ідентифікатори, але не текст клієнта.
Скасування поширюється на шлюз, а помилки переводять чернетку в
термінальний стан замість того, щоб лишити її запущеною.
"""

import datetime
import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

from . import drafting, gateway, telemetry
from .providers.base import ProviderError

log = logging.getLogger("app.jobs")

# Статуси, після яких подій більше не буде.
TERMINAL = {"done", "failed", "cancelled"}
MAX_DRAFT_HISTORY = 200


@dataclass
class Draft:
    """Стан однієї чернетки — те, що зберігається в реєстрі і йде на
    сторінку як знімок.

    `status` — `queued`, `running`, `done`, `failed`, `cancelled`.
    `text` — накопичений текст. `attempts`, `provider`, `model`,
    `fallback` — звідки взявся результат. `error` — остаточна помилка,
    якщо є: `kind`, `message`, `retryable`. `elapsed` — секунди, наприклад
    `{"first_token": 0.8, "total": 4.1}`. `warnings` — зауваження до
    чернетки з `drafting.check`. `events` — журнал подій для потоку;
    у знімок на сторінку не входить.
    """

    draft_id: str
    request_id: str
    client: str
    status: str = "queued"
    text: str = ""
    attempts: int = 0
    provider: str | None = None
    model: str | None = None
    fallback: bool = False
    cached: bool = False
    cost: float | None = None
    cost_estimated: bool = False
    error: dict | None = None
    usage: dict | None = None
    elapsed: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    fresh: bool = False
    http_request_id: str | None = None
    events: list[dict] = field(default_factory=list)


_drafts: dict[str, Draft] = {}
_order: list[str] = []
_lock = threading.RLock()
_changed = threading.Condition(_lock)
_cancellations: dict[str, threading.Event] = {}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def new_draft(request_id: str, client: str) -> Draft:
    """Створити чернетку зі статусом `queued` і зареєструвати її.
    Роботу не запускає — це справа `start`."""
    draft = Draft(draft_id=uuid.uuid4().hex[:8], request_id=request_id, client=client,
                  created_at=_now(), updated_at=_now())
    with _lock:
        _drafts[draft.draft_id] = draft
        _order.insert(0, draft.draft_id)
        while len(_order) > MAX_DRAFT_HISTORY:
            oldest_terminal = next(
                (draft_id for draft_id in reversed(_order)
                 if draft_id != draft.draft_id and _drafts[draft_id].status in TERMINAL),
                None,
            )
            if oldest_terminal is None:
                break
            _order.remove(oldest_terminal)
            _drafts.pop(oldest_terminal, None)
    return draft


def get(draft_id: str) -> Draft | None:
    with _lock:
        return _drafts.get(draft_id)


def list_drafts(limit: int = 50) -> list[Draft]:
    """Чернетки, нові першими."""
    with _lock:
        return [_drafts[i] for i in _order[:limit]]


def emit(draft: Draft, event: str, data: dict | None = None) -> None:
    """Додати подію до журналу чернетки й розбудити підписників.

    Статус і текст чернетки ця функція не змінює — це робить фонова
    робота разом із подією, під тим самим замком, якщо їй потрібна
    узгодженість між знімком і потоком.
    """
    with _changed:
        draft.events.append({"id": len(draft.events) + 1, "event": event, "data": data or {}})
        draft.updated_at = _now()
        _changed.notify_all()


def subscribe(draft_id: str, since: int = 0, heartbeat: float = 15.0) -> Iterator[dict | None]:
    """Віддавати події чернетки, починаючи з номера `since + 1`.

    Спершу — ті, що вже є, потім — нові в міру надходження. Завершується,
    коли чернетка в кінцевому статусі й усі події віддано, або коли
    чернетки немає. Якщо подій немає довше за `heartbeat` секунд, віддає
    `None`: веб-рівень надсилає порожній коментар, щоб зʼєднання не
    закрив проксі і щоб помітити, що клієнт відключився.
    """
    while True:
        with _changed:
            draft = _drafts.get(draft_id)
            if draft is None:
                return
            pending = draft.events[since:]
            if not pending:
                if draft.status in TERMINAL:
                    return
                _changed.wait(timeout=heartbeat)
                pending = draft.events[since:]
        if not pending:
            yield None
            continue
        for event in pending:
            yield event
        since += len(pending)


def start(sample: dict, client: str, fresh: bool = False) -> Draft:
    """Створити чернетку для звернення `sample` і запустити генерацію у
    фоні. Повертає чернетку одразу — найімовірніше, ще `queued`.
    `fresh` — оминути кеш (кнопка «Повторити»)."""
    http_request_id = telemetry.request_id_var.get()
    draft = new_draft(str(sample.get("id", "")), client)
    draft.fresh = fresh
    draft.http_request_id = http_request_id
    cancelled = threading.Event()
    with _lock:
        _cancellations[draft.draft_id] = cancelled
    extra = {
        "request_id": http_request_id,
        "draft_id": draft.draft_id,
        "sample_id": draft.request_id,
        "client_id": hashlib.sha256(client.encode("utf-8")).hexdigest()[:12],
        "fresh": fresh,
    }
    log.info("draft.created", extra=extra)
    emit(draft, "status", {"status": "queued"})

    def run() -> None:
        started = time.monotonic()
        try:
            request = drafting.build_request(sample)
            request.metadata.update({
                "draft_id": draft.draft_id,
                "http_request_id": http_request_id,
                "client_id": extra["client_id"],
                "fresh": fresh,
            })

            def on_delta(text: str) -> None:
                with _changed:
                    if cancelled.is_set():
                        return
                    draft.text += text
                    draft.status = "running"
                    emit(draft, "delta", {"text": text})

            def on_status(data: dict) -> None:
                with _changed:
                    if cancelled.is_set():
                        return
                    draft.status = "running"
                    draft.attempts = max(draft.attempts, int(data.get("attempt", 0) or 0))
                    draft.provider = data.get("provider", draft.provider)
                    draft.model = data.get("model", draft.model)
                    draft.fallback = bool(data.get("fallback", draft.fallback))
                    draft.cached = bool(data.get("cached", draft.cached))
                    emit(draft, "status", {"status": "running", **data})

            result = gateway.generate(request, on_delta, on_status, cancelled.is_set)
            with _changed:
                if cancelled.is_set():
                    draft.status = "cancelled"
                    emit(draft, "cancelled")
                    return
                draft.text = result.text
                draft.provider = result.provider
                draft.model = result.model
                draft.usage = result.usage
                draft.elapsed = {
                    "first_token": request.metadata.get("first_token_seconds"),
                    "total": time.monotonic() - started,
                }
                draft.attempts = int(request.metadata.get("attempts", draft.attempts) or draft.attempts)
                draft.fallback = bool(request.metadata.get("fallback", False))
                draft.cached = result.cached
                draft.cost = result.cost
                draft.cost_estimated = result.cost_estimated
                draft.warnings = drafting.check(result.text, sample)
                draft.status = "done"
                done_data = {
                    "text": draft.text, "provider": draft.provider, "model": draft.model,
                    "usage": draft.usage, "elapsed": draft.elapsed, "attempts": draft.attempts,
                    "fallback": draft.fallback, "cached": draft.cached, "cost": draft.cost,
                    "cost_estimated": draft.cost_estimated, "warnings": draft.warnings,
                }
                emit(draft, "done", done_data)
            log.info("draft.done", extra={
                **extra, "attempts": draft.attempts, "provider": draft.provider,
                "model": draft.model, "fallback": draft.fallback, "cached": draft.cached,
                "cost": draft.cost, "cost_estimated": draft.cost_estimated,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            })
        except ProviderError as exc:
            with _changed:
                if cancelled.is_set() or exc.kind == "cancelled":
                    draft.status = "cancelled"
                    emit(draft, "cancelled")
                    log.info("draft.cancelled", extra={**extra, "duration_ms": round(
                        (time.monotonic() - started) * 1000, 1)})
                else:
                    draft.status = "failed"
                    draft.error = {"kind": exc.kind, "message": exc.message,
                                   "retryable": exc.retryable,
                                   "request_id": http_request_id}
                    emit(draft, "error", draft.error)
                    log.error("draft.failed", extra={
                        **extra, "kind": exc.kind, "attempts": draft.attempts,
                        "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    })
        except Exception as exc:
            with _changed:
                draft.status = "failed"
                draft.error = {"kind": "unknown", "message": "Не вдалося створити чернетку.",
                               "retryable": False}
                emit(draft, "error", draft.error)
            log.error("draft.failed", extra={
                **extra, "kind": "unknown", "error_type": type(exc).__name__,
            })
        finally:
            with _lock:
                _cancellations.pop(draft.draft_id, None)

    threading.Thread(target=run, name=f"draft-{draft.draft_id}", daemon=True).start()
    return draft


def cancel(draft_id: str) -> Draft:
    """Попросити фонову роботу зупинитися. Повертає чернетку; якщо її
    немає або вона вже завершена — вирішуєте ви."""
    with _lock:
        draft = _drafts.get(draft_id)
        if draft is None:
            raise KeyError(draft_id)
        if draft.status in TERMINAL:
            raise ValueError(f"Чернетка вже завершена зі статусом {draft.status}.")
        cancellation = _cancellations.get(draft_id)
        if cancellation is None:
            raise ValueError("Чернетку неможливо скасувати.")
        cancellation.set()
    log.info("draft.cancel_requested", extra={
        "request_id": draft.http_request_id, "draft_id": draft.draft_id,
        "sample_id": draft.request_id,
    })
    return draft
