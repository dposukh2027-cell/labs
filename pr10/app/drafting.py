"""Що саме просимо в моделі: чернетка відповіді клієнтові."""

from . import gateway
from .providers.base import Request


def build_request(sample: dict) -> Request:
    """Скласти запит до моделі за зразком звернення."""
    facts = "\n".join(f"- {fact}" for fact in sample.get("facts", []))
    text = sample.get("text", "")
    message = (
        "Ти — оператор підтримки інтернет-магазину «Сузірʼя». "
        "Пиши українською мовою, ввічливо, коротко, але достатньо конкретно. "
        "Спирайся лише на наведені факти. Не вигадуй строки, суми, терміни, адреси, "
        "номер заявки, умови або альтернативи, яких немає в фактах. "
        "Якщо подробиці відсутні, скажи відкрито, що вони не вказані. "
        "Не повторюй слова клієнта, а формулюй відповідь як відповідь служби підтримки.\n\n"
        f"ФАКТИ:\n{facts}\n\n"
        f"ТЕКСТ КЛІЄНТА:\n{text}\n\n"
        "Склади коротку, вічливу чернетку відповіді клієнтові, яка містить лише те, "
        "що можна підтвердити за фактами."
    )
    return Request(
        messages=[
            {"role": "system", "content": "Ти — оператор підтримки інтернет-магазину, працюєш українською мовою."},
            {"role": "user", "content": message},
        ],
        max_tokens=gateway.MAX_TOKENS,
        temperature=gateway.TEMPERATURE,
        model=sample.get("model") or gateway.MODEL,
        metadata={"request_id": sample.get("id"), "customer": sample.get("customer"), "kind": sample.get("kind")},
    )


def check(text: str, sample: dict) -> list[str]:
    """Перевірити готову чернетку й повернути перелік попереджень для оператора."""
    warnings: list[str] = []
    lower = text.lower()
    facts = sample.get("facts", [])
    fact_text = "\n".join(facts).lower()

    if sample.get("expect") and "номер заявки" in sample["expect"].lower():
        if not any(token in lower for token in ("r-500", "r-", "заявка")):
            warnings.append("У відповіді не вказано номер заявки або його можна не відрізнити.")

    suspicious_terms = ["якщо", "можливо", "можна", "або", "випадок", "додатково", "навіть якщо"]
    if any(term in lower for term in suspicious_terms):
        warnings.append("У відповіді є формулювання, які можуть виглядати як вигадані умови або альтернативи.")

    for fact in facts:
        fact_keywords = [token for token in fact.lower().split() if len(token) > 4 and token.strip(".,;:-")]
        if not fact_keywords:
            continue
        if sample.get("kind") and "відмова" in sample["kind"].lower() and "не підлягає" in fact.lower() and "не підлягає" not in lower:
            warnings.append("У відповіді може бракувати пояснення, чому повернення заборонене.")

    if "повернення" in lower and "не підлягає" not in lower and sample.get("expect") and "відмова" in sample["expect"].lower():
        warnings.append("У відповіді має бути чітка відмова, а не «може бути» або «спробуємо».")

    if not any(key in lower for key in ("з повагою", "слава", "служби підтримки")):
        warnings.append("У відповіді бракує ввічливої підпису служби підтримки.")

    if not text.strip():
        warnings.append("Чернетка порожня.")

    return warnings
