"""Фонові задачі: чернетка генерується не в HTTP-запиті, а окремо.

`POST /api/drafts` повертається одразу з номером чернетки, а робота
триває у фоні: сторінка дізнається про стан через потік подій
(`GET /api/drafts/{id}/events`) або знімок (`GET /api/drafts/{id}`) і
може скасувати її (`POST /api/drafts/{id}/cancel`). Так чернетка не
прив'язана до одного HTTP-зʼєднання: сторінку можна перезавантажити,
а потім відкрити ту саму чернетку й побачити все, що встигло статися.

Модуль не знає, як влаштований шлюз і що саме генерується; він знає
лише `Draft`, події і те, що робота виконується не в потоці запиту.

Що тут дано готовим — реєстр чернеток і події. `emit` додає подію до
журналу чернетки й будить тих, хто чекає; `subscribe` віддає події
від указаного номера і далі в міру надходження, доки чернетка не
дійде до кінцевого статусу. Веб-рівень перетворює це на
server-sent events; реалізація фонової роботи до цього не торкається.

Заготовки — `start` і `cancel`. Рішення з розділу 2 практичної роботи:

* у чому виконувати: потік на чернетку, пул потоків, asyncio-задача?
  Що обмежує кількість одночасних робіт — це чи шлюз;
* порядок дій у фоновій роботі: яку подію й який статус виставити
  спершу, що робити з фрагментами, що — з результатом і з помилкою.
  Жоден виняток не має лишити чернетку в стані `running`;
* скасування — спільне: фонова робота сама перевіряє прапорець між
  фрагментами й спробами. Хто його ставить, де він живе, що
  відбувається з текстом, який уже надіслано, і чи може скасована
  чернетка потім стати `done`, якщо потік завершився пізніше;
* `cancel` для чернетки, яка вже завершена чи не існує, — помилка якого
  роду і з яким HTTP-статусом;
* що буває зі старими чернетками: реєстр у памʼяті росте з кожною.
  Скільки тримати і коли прибирати.

Події, які розуміє сторінка (інші вона показує як є):

    status     {"status": "running", "attempt": 1, "provider": "openai",
                "fallback": false, "detail": "…"}
    delta      {"text": "…"}                      приріст тексту
    done       {"text": "…", "provider": "…", "model": "…",
                "usage": {...}, "elapsed": {...}, "attempts": 2,
                "fallback": false, "warnings": ["…"]}
    error      {"kind": "timeout", "message": "…", "retryable": true}
    cancelled  {}

Поля — відправна точка; змінюючи їх, змініть і сторінку.
"""

import datetime
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

from . import drafting, gateway
from .providers.base import ProviderError

# Статуси, після яких подій більше не буде.
TERMINAL = {"done", "failed", "cancelled"}


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
    error: dict | None = None
    usage: dict | None = None
    elapsed: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    events: list[dict] = field(default_factory=list)


_drafts: dict[str, Draft] = {}
_order: list[str] = []
_lock = threading.Lock()
_changed = threading.Condition(_lock)


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


def start(sample: dict, client: str) -> Draft:
    """Створити чернетку для звернення `sample` і запустити генерацію у
    фоні. Повертає чернетку одразу — найімовірніше, ще `queued`."""
    draft = new_draft(sample["id"], client)
    with _lock:
        draft.status = "queued"
    emit(draft, "status", {"status": "queued"})

    def runner() -> None:
        start_monotonic = time.monotonic()
        request = drafting.build_request(sample)
        last_status = {"attempt": 0, "provider": None, "fallback": False}
        first_token_elapsed = None
        try:
            with _lock:
                draft.status = "running"
                draft.attempts = 0
                draft.provider = None
                draft.model = None
                draft.fallback = False
                draft.error = None
            emit(draft, "status", {"status": "running", "attempt": 1, "provider": "pending"})

            def on_delta(text: str) -> None:
                nonlocal first_token_elapsed
                with _lock:
                    draft.text += text
                    if first_token_elapsed is None:
                        first_token_elapsed = time.monotonic() - start_monotonic
                emit(draft, "delta", {"text": text})

            def on_status(info: dict) -> None:
                nonlocal last_status
                with _lock:
                    draft.attempts = int(info.get("attempt", draft.attempts or 0))
                    draft.provider = info.get("provider") or draft.provider
                    draft.model = info.get("model") or draft.model
                    draft.fallback = bool(info.get("fallback", draft.fallback))
                    last_status = {
                        "attempt": draft.attempts,
                        "provider": draft.provider,
                        "fallback": draft.fallback,
                    }
                emit(draft, "status", {"status": "running", **info})

            def is_cancelled() -> bool:
                with _lock:
                    return draft.status == "cancelled"

            result = gateway.generate(request, on_delta, on_status, is_cancelled)
            warnings = drafting.check(result.text, sample)
            with _lock:
                draft.status = "done"
                draft.text = result.text
                draft.attempts = result.attempts
                draft.provider = result.provider
                draft.model = result.model
                draft.usage = result.usage
                draft.elapsed = {
                    "total": round(time.monotonic() - start_monotonic, 2),
                    "first_token": round(first_token_elapsed, 2) if first_token_elapsed is not None else None,
                }
                draft.warnings = warnings
                draft.error = None
            emit(draft, "done", {
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
                "usage": result.usage,
                "elapsed": draft.elapsed,
                "attempts": result.attempts,
                "fallback": draft.fallback,
                "warnings": warnings,
            })
        except ProviderError as exc:
            with _lock:
                draft.status = "failed"
                draft.error = {"kind": exc.kind, "message": exc.message, "retryable": exc.retryable}
            emit(draft, "error", draft.error)
        except Exception as exc:  # pragma: no cover
            with _lock:
                draft.status = "failed"
                draft.error = {"kind": "unknown", "message": str(exc), "retryable": False}
            emit(draft, "error", draft.error)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return draft


def cancel(draft_id: str) -> Draft:
    """Попросити фонову роботу зупинитися. Повертає чернетку."""
    with _lock:
        draft = _drafts.get(draft_id)
        if draft is None:
            raise KeyError(f"Чернетка {draft_id} не знайдена")
        if draft.status in TERMINAL:
            raise ValueError(f"Чернетка {draft_id} вже завершена")
        draft.status = "cancelled"
        draft.error = {"kind": "cancelled", "message": "Генерацію скасовано", "retryable": False}
    emit(draft, "cancelled", {})
    return draft
