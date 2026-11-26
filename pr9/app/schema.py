"""Контракт кроку розбору: що модель має витягти зі звернення клієнта
і як це перевіряється.

Окремий модуль, як у ПР4, ПР6 і ПР7: схема — домовленість між моделлю
та рештою workflow. Наступні кроки працюють лише з тим, що пройшло
перевірку тут, і не бачать сирого тексту відповіді моделі.

Що має дати розбір (розділ 2 практичної роботи): вид звернення —
повернення товару, скасування замовлення, питання про стан замовлення
або щось інше; номер замовлення, якщо клієнт його назвав; товар, як
клієнт його назвав; причину повернення.

Рішення — ваші:

* які поля й що з них обовʼязкове; як модель каже «номер не названо» і
  «не розумію, про що звернення» — і чи це одне й те саме;
* причина повернення: категорія сервісу (`not_suitable`, `defect`, …),
  слова клієнта чи обидва? Хто вирішує категорію — модель чи ваш код за
  словами клієнта? Згадайте q11 із ПР8;
* що робити зі зверненням, у якому дві дії, — схема це дозволяє чи ні;
* чи просити від моделі щось понад потрібне наступним крокам — і чи буде
  кому цим скористатися;
* що в цій схемі статичне, а що будується з даних: наприклад, вибір
  товару з позицій конкретного замовлення — це окремий крок із власною
  схемою, `enum` якої складається з результату інструмента.

Описати схему можна JSON Schema вручну або pydantic-моделлю.
"""


import copy
import json

from jsonschema import Draft7Validator

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["return", "cancel", "status", "other"],
        },
        "order_id": {"type": ["string", "null"]},
        "item": {"type": ["string", "null"]},
        "reason": {
            "type": ["string", "null"],
            "enum": ["not_suitable", "defect", "wrong_item", "damaged", None],
        },
    },
    "required": ["kind", "order_id", "item", "reason"],
    "additionalProperties": False,
}


def request_schema() -> dict:
    """Повернути JSON Schema результату розбору звернення."""
    return copy.deepcopy(SCHEMA)


def validate(raw: str | dict) -> dict:
    """Перевірити сиру відповідь моделі на кроці розбору."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"відповідь моделі не є JSON: {exc.msg}") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("розбір звернення має бути JSON-об'єктом або рядком JSON")

    validator = Draft7Validator(SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(
            f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        )
        raise ValueError(f"відповідь моделі не проходить схему: {detail}")

    payload = {
        "kind": str(data["kind"]),
        "order_id": data.get("order_id"),
        "item": data.get("item"),
        "reason": data.get("reason"),
    }
    if payload["order_id"] is not None:
        payload["order_id"] = str(payload["order_id"]).strip() or None
    if payload["item"] is not None:
        payload["item"] = str(payload["item"]).strip() or None
    if payload["reason"] is not None:
        payload["reason"] = str(payload["reason"]).strip() or None
    return payload
