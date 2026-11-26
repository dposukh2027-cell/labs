"""Контракт відповіді моделі: які поля вона має повернути й як це
перевіряється.

Окремий модуль, як у ПР4 і ПР6: схема — домовленість між моделлю та
рештою застосунку, і від провайдера вона не залежить. `app/rules.py` і
`app/extraction.py` працюють лише з тим, що пройшло перевірку тут.

Набір полів задано (розділ 2 практичної роботи):

* тип документа — рахунок на оплату чи інший документ;
* номер рахунку, дата, строк дії (якщо є);
* постачальник: назва, код (ЄДРПОУ або РНОКПП), IBAN;
* покупець: назва, код;
* позиції: найменування, одиниця, кількість, ціна, сума;
* разом без ПДВ, ПДВ, усього до сплати.

Рішення — ваші:

* як назвати поля й що з них обовʼязкове в схемі;
* у якому вигляді повертати дату, суму, IBAN — як надруковано чи
  нормалізовано, і хто нормалізує: модель чи ваш код;
* як модель позначає значення, якого в документі немає, і значення,
  яке є, але не читається, — і чи це одне й те саме;
* чи просити від моделі щось понад задані поля (упевненість, фрагмент
  тексту, з якого взято значення) — і чи буде кому цим скористатися.

Описати схему можна JSON Schema вручну або pydantic-моделлю.
"""

import json
from decimal import Decimal

from jsonschema import Draft202012Validator, FormatChecker


class SchemaValidationError(ValueError):
    """Відповідь моделі не відповідає контракту."""


def _nullable(value_type: str, **extra: object) -> dict:
    return {"type": [value_type, "null"], **extra}


def output_schema() -> dict:
    """Повернути JSON Schema відповіді моделі.

    Та сама схема передається моделі як опис очікуваного результату
    (через `response_format` або текстом в інструкції) і використовується
    для перевірки того, що повернулося.
    """
    nullable_text = _nullable("string")
    nullable_date = _nullable("string", format="date")
    nullable_number = _nullable("number", minimum=0, maximum=1_000_000_000_000)
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "unit", "quantity", "unit_price", "amount"],
        "properties": {
            "name": nullable_text,
            "unit": nullable_text,
            "quantity": _nullable("number", exclusiveMinimum=0, maximum=1_000_000_000),
            "unit_price": nullable_number,
            "amount": nullable_number,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "document_type", "number", "date", "valid_until", "supplier",
            "buyer", "items", "total_without_vat", "vat", "total",
        ],
        "properties": {
            "document_type": {
                "type": ["string", "null"],
                "enum": ["рахунок", "інший документ", None],
            },
            "number": nullable_text,
            "date": nullable_date,
            "valid_until": nullable_date,
            "supplier": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "code", "iban"],
                "properties": {
                    "name": nullable_text,
                    "code": nullable_text,
                    "iban": nullable_text,
                },
            },
            "buyer": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "code"],
                "properties": {
                    "name": nullable_text,
                    "code": nullable_text,
                },
            },
            "items": {"type": "array", "items": item_schema},
            "total_without_vat": nullable_number,
            "vat": nullable_number,
            "total": nullable_number,
        },
    }


def validate(raw: str) -> dict:
    """Перевірити сиру відповідь моделі й повернути дані, яким можна
    довіряти структурно.

    Якщо текст не є JSON або не проходить схему — підняти помилку з
    поясненням, що саме не так.

    Схема перевіряє форму: що сума — число, дата — дата, позиції — список.
    Чи сходиться сума з позиціями і чи існує такий IBAN — перевірка
    змісту, і її місце в `app/rules.py`.
    """
    def reject_constant(value: str) -> None:
        raise ValueError(f"недопустиме числове значення {value}")

    try:
        data = json.loads(raw, parse_float=Decimal, parse_constant=reject_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SchemaValidationError(f"Відповідь моделі не є коректним JSON: {exc}") from exc

    validator = Draft202012Validator(output_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda error: list(map(str, error.absolute_path)))
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "відповідь"
        raise SchemaValidationError(f"Поле «{path}»: {error.message}")
    return data
