"""Програмні правила: перевірка змісту вилучених даних.

Схема (`app/schema.py`) каже, що IBAN — рядок, а сума — число. Чи це
справжній IBAN і чи сходиться сума з позиціями, схема не знає. Це знає
документ: у рахунку багато надлишковості — контрольні розряди в кодах,
підсумки, що мають дорівнювати сумі рядків, ПДВ, що має дорівнювати
п'ятій частині. Модель, яка прочитала 8 замість 3, цю надлишковість
порушує, і код це бачить. Правила тут не знають ні про модель, ні про
веб-рівень: на вході — перевірений за схемою словник, на виході — перелік
знайдених проблем.

Набір правил задано (розділ 2 практичної роботи):

* IBAN: формат і контрольне число за ISO 13616 (залишок mod 97);
* код постачальника й покупця: 8 цифр ЄДРПОУ з контрольним розрядом
  або 10 цифр РНОКПП;
* арифметика: кількість × ціна = сума в кожному рядку; сума рядків =
  разом без ПДВ; ПДВ = 20 % (або нуль для неплатника); разом + ПДВ =
  до сплати — з допуском на округлення, який ви оберете й обґрунтуєте;
* дати: існують, не з майбутнього, строк дії не раніше дати рахунку;
* покупець — ваша компанія (`reference/company.json`);
* постачальник відомий, і IBAN збігається з довідником
  (`reference/suppliers.json`);
* обовʼязкові поля присутні.

Помилки правил блокують `auto`; відсутнє обовʼязкове значення окремо
позначається, а гроші рахуються через `Decimal` з округленням до копійок.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import unicodedata

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"


@dataclass
class Issue:
    """Проблема, знайдена правилом.

    `field` — шлях до поля, наприклад `supplier.iban` чи `items.1.amount`
    (другий рядок: індекс — з нуля); сторінка підсвічує поле з таким
    шляхом. `rule` — коротка назва
    правила. `message` — пояснення для людини, яка перевірятиме документ.
    `severity` — `error` або `warning`; що з цього випливає для рішення,
    вирішує `app/extraction.py`.
    """

    field: str
    rule: str
    message: str
    severity: str = "error"


def load_reference() -> tuple[dict, list[dict]]:
    """Прочитати реквізити своєї компанії й довідник постачальників."""
    company = json.loads((REFERENCE_DIR / "company.json").read_text(encoding="utf-8"))
    suppliers = json.loads((REFERENCE_DIR / "suppliers.json").read_text(encoding="utf-8"))
    return company, suppliers


def check(document: dict) -> list[Issue]:
    """Застосувати правила до вилученого документа.

    Порожній перелік означає, що правила нічого не знайшли, — а не що
    документ прочитано правильно. Різниця між цими двома речами і є
    предметом перевірки на наборі зразків.
    """
    issues: list[Issue] = []
    company, suppliers = load_reference()

    def issue(field: str, rule: str, message: str) -> None:
        issues.append(Issue(field, rule, message))

    def decimal(value: object) -> Decimal | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return number if number.is_finite() else None

    def money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def normalized_name(value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return "".join(char for char in text if char.isalnum())

    def normalized_code(value: object) -> str:
        return re.sub(r"\D", "", str(value or ""))

    def valid_tax_code(value: object) -> tuple[bool, str]:
        code = normalized_code(value)
        if len(code) == 10:
            digits = [int(char) for char in code]
            weights = (-1, 5, 7, 9, 4, 6, 10, 5, 7)
            return (sum(digit * weight for digit, weight in zip(digits[:9], weights)) % 11 == digits[9],
                    "РНОКПП")
        if len(code) == 8:
            digits = [int(char) for char in code]
            first = digits[0]
            weights = (
                list(range(1, 8)) if first <= 2
                else [7, 1, 2, 3, 4, 5, 6] if first <= 5
                else [3, 4, 5, 6, 7, 1, 2]
            )
            checksum = sum(digit * weight for digit, weight in zip(digits[:7], weights)) % 11
            if checksum == 10:
                alternate = (9, 10, 5, 8, 4, 2, 1)
                checksum = sum(digit * weight for digit, weight in zip(digits[:7], alternate)) % 11
            return checksum == digits[7], "ЄДРПОУ"
        return False, ""

    def check_code(field: str, value: object) -> None:
        code = normalized_code(value)
        if not code:
            return
        if len(code) not in (8, 10) or not str(value).strip().isdigit():
            issue(field, "code_format", "Код має містити лише 8 цифр ЄДРПОУ або 10 цифр РНОКПП.")
        else:
            is_valid, code_type = valid_tax_code(code)
            if not is_valid:
                issue(field, "code_checksum", f"Контрольний розряд коду {code_type} не збігається.")

    def check_iban(value: object) -> str:
        iban = re.sub(r"\s+", "", str(value or "")).upper()
        if not iban:
            return iban
        if not re.fullmatch(r"UA\d{27}", iban):
            issue("supplier.iban", "iban_format", "IBAN має містити UA і ще 27 цифр.")
            return iban
        rearranged = iban[4:] + iban[:4]
        remainder = 0
        for char in rearranged:
            expanded = str(ord(char) - ord("A") + 10) if char.isalpha() else char
            for digit in expanded:
                remainder = (remainder * 10 + int(digit)) % 97
        if remainder != 1:
            issue("supplier.iban", "iban_checksum", "Контрольна сума IBAN неправильна.")
        return iban

    def required(field: str, value: object) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            issue(field, "missing_required", "Обовʼязкове поле відсутнє або не читається.")

    for field in ("document_type", "number", "date"):
        required(field, document.get(field))
    supplier = document.get("supplier") or {}
    buyer = document.get("buyer") or {}
    for key in ("name", "code", "iban"):
        required(f"supplier.{key}", supplier.get(key))
    for key in ("name", "code"):
        required(f"buyer.{key}", buyer.get(key))

    doc_type = document.get("document_type")
    if doc_type and doc_type != "рахунок":
        issue("document_type", "document_type", "Документ не є рахунком на оплату.")

    check_code("supplier.code", supplier.get("code"))
    check_code("buyer.code", buyer.get("code"))
    iban = check_iban(supplier.get("iban"))

    try:
        invoice_date = date.fromisoformat(document["date"]) if document.get("date") else None
    except (TypeError, ValueError):
        invoice_date = None
        issue("date", "date_invalid", "Дата рахунку некоректна.")
    if invoice_date and invoice_date > date.today():
        issue("date", "date_future", "Дата рахунку не може бути в майбутньому.")
    try:
        valid_until = date.fromisoformat(document["valid_until"]) if document.get("valid_until") else None
    except (TypeError, ValueError):
        valid_until = None
        issue("valid_until", "date_invalid", "Строк дії рахунку некоректний.")
    if invoice_date and valid_until and valid_until < invoice_date:
        issue("valid_until", "date_order", "Строк дії не може бути раніше дати рахунку.")

    company_code = str(company.get("code", ""))
    buyer_code = normalized_code(buyer.get("code"))
    if buyer_code and buyer_code != company_code:
        issue("buyer.code", "buyer", "Рахунок виставлено не компанії «Сузірʼя Рітейл».")
    if buyer.get("name") and normalized_name(buyer["name"]) != normalized_name(company.get("name")):
        issue("buyer.name", "buyer", "Назва покупця не збігається з «Сузірʼя Рітейл».")

    supplier_code = normalized_code(supplier.get("code"))
    registered_supplier = next(
        (entry for entry in suppliers if normalized_code(entry.get("code")) == supplier_code),
        None,
    )
    if supplier_code and registered_supplier is None:
        issue("supplier.code", "supplier_registry", "Постачальника немає у довіднику.")
    if registered_supplier:
        if supplier.get("name") and normalized_name(supplier["name"]) != normalized_name(registered_supplier["name"]):
            issue("supplier.name", "supplier_registry", "Назва постачальника не збігається з довідником.")
        if iban and iban != re.sub(r"\s+", "", registered_supplier.get("iban", "")).upper():
            issue("supplier.iban", "iban_registry", "IBAN не збігається з рахунком у довіднику постачальників.")

    items = document.get("items") or []
    if not items:
        issue("items", "missing_required", "У рахунку має бути щонайменше одна позиція.")
    line_amounts: list[Decimal] = []
    for index, item in enumerate(items):
        for key in ("name", "unit", "quantity", "unit_price", "amount"):
            required(f"items.{index}.{key}", item.get(key))
        quantity = decimal(item.get("quantity"))
        unit_price = decimal(item.get("unit_price"))
        amount = decimal(item.get("amount"))
        if amount is not None:
            line_amounts.append(money(amount))
        if quantity is not None and unit_price is not None and amount is not None:
            expected_amount = money(quantity * unit_price)
            if abs(expected_amount - money(amount)) > Decimal("0.01"):
                issue(
                    f"items.{index}.amount",
                    "arithmetic_line",
                    f"Сума позиції не дорівнює кількості × ціні ({expected_amount:.2f}).",
                )

    subtotal = decimal(document.get("total_without_vat"))
    vat = decimal(document.get("vat"))
    total = decimal(document.get("total"))
    for field, value in (
        ("total_without_vat", subtotal),
        ("vat", vat),
        ("total", total),
    ):
        required(field, value)
    if line_amounts and subtotal is not None:
        items_sum = money(sum(line_amounts, Decimal("0")))
        if abs(items_sum - money(subtotal)) > Decimal("0.01"):
            issue("total_without_vat", "arithmetic_subtotal", f"Разом без ПДВ не збігається із сумою позицій ({items_sum:.2f}).")
    if subtotal is not None and vat is not None and total is not None:
        expected_total = money(subtotal + vat)
        if abs(expected_total - money(total)) > Decimal("0.01"):
            issue("total", "arithmetic_total", f"Усього до сплати не дорівнює сумі без ПДВ плюс ПДВ ({expected_total:.2f}).")
        if registered_supplier:
            expected_vat = money(subtotal * Decimal("0.20")) if registered_supplier.get("vat_payer") else Decimal("0.00")
            if abs(expected_vat - money(vat)) > Decimal("0.01"):
                message = (
                    f"ПДВ має бути {expected_vat:.2f} за статусом постачальника у довіднику."
                )
                issue("vat", "arithmetic_vat", message)

    return issues
