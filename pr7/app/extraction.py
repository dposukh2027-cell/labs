"""Конвеєр обробки документа: від байтів файлу до рішення, що з ним робити.

Єдине місце, яке знає всі кроки послідовно: підготувати зображення
(`images.prepare`), вилучити поля (`llm.extract`), перевірити їх
правилами (`rules.check`) і вирішити долю документа. Учасники одне про
одного не знають: модуль зображень — про модель, модель — про правила,
правила — про веб-рівень.

Рішення про документ — одне з трьох:

* `auto` — дані можна передати в реєстр платежів без людини;
* `review` — дані є, але їх має переглянути людина: причини перелічено;
* `reject` — це не рахунок на оплату або з документа нічого не взяти.

Рішення ухвалює код за результатами перевірок, а не модель. `auto`
можливий лише без жодної знайденої проблеми; невідомі обовʼязкові
значення ведуть на перевірку, а не рахуються з інших полів.
"""

from dataclasses import dataclass, field
from time import perf_counter

from . import images, llm
from .rules import Issue
from . import rules

MAX_UPLOAD_BYTES = images.UPLOAD_MAX_BYTES


class ProcessingError(Exception):
    """Помилка конвеєра, яку веб-рівень може безпечно показати клієнту."""

    def __init__(self, message: str, status_code: int, raw_response: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


@dataclass
class Result:
    """Результат конвеєра — те, з чим працює веб-рівень.

    `decision` — `auto`, `review` або `reject`; `reasons` — чому саме так,
    словами для людини. `document` — поля, які повернула модель і які
    пройшли схему (або `None`, якщо до цього не дійшло). `issues` —
    проблеми, знайдені правилами. `image` — розміри до й після підготовки.
    `elapsed` — час за етапами, наприклад `{"prepare": 0.05,
    "extraction": 6.8, "checks": 0.001}`. `usage` — токени, якщо модель
    викликалась.
    """

    decision: str
    reasons: list[str] = field(default_factory=list)
    document: dict | None = None
    issues: list[Issue] = field(default_factory=list)
    image: dict = field(default_factory=dict)
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None
    raw_response: str | None = None


def decide(document: dict, issues: list[Issue]) -> tuple[str, list[str]]:
    """Вирішити долю документа за вилученими полями й знайденими
    проблемами. Повертає рішення і його причини."""
    if document.get("document_type") and document["document_type"] != "рахунок":
        return "reject", ["Документ не є рахунком на оплату."]

    meaningful = any((
        document.get("number"),
        document.get("date"),
        (document.get("supplier") or {}).get("name"),
        (document.get("buyer") or {}).get("name"),
        document.get("items"),
        document.get("total"),
    ))
    if not meaningful:
        return "reject", ["З документа не вдалося вилучити достатньо даних."]
    if issues:
        return "review", [item.message for item in issues]
    return "auto", ["Обовʼязкові поля та всі програмні перевірки пройдено."]


def process(content: bytes) -> Result:
    """Обробити файл: підготувати → вилучити → перевірити → вирішити."""
    started = perf_counter()
    try:
        prepared = images.prepare(content)
    except images.ImageError as exc:
        raise ProcessingError(str(exc), exc.status_code) from exc
    prepare_elapsed = perf_counter() - started

    extraction_started = perf_counter()
    try:
        extracted = llm.extract(prepared)
    except llm.LLMError as exc:
        raise ProcessingError(str(exc), exc.status_code, exc.raw_response) from exc
    extraction_elapsed = perf_counter() - extraction_started

    checks_started = perf_counter()
    issues = rules.check(extracted["document"])
    decision, reasons = decide(extracted["document"], issues)
    checks_elapsed = perf_counter() - checks_started

    return Result(
        decision=decision,
        reasons=reasons,
        document=extracted["document"],
        issues=issues,
        image={"original": prepared.original, "sent": prepared.sent},
        model=extracted["model"],
        elapsed={
            "prepare": prepare_elapsed,
            "extraction": extraction_elapsed,
            "checks": checks_elapsed,
        },
        usage=extracted.get("usage"),
        raw_response=extracted.get("raw_response"),
    )
