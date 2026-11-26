"""Інструменти помічника: що модель може попросити виконати і як це
перевіряється.

Єдине місце застосунку, яке знає і про модель, і про сервіс магазину
(`shop/service.py`). Тут описано інструменти для моделі, тут перевіряють
аргументи, які вона повернула, і тут викликають сервіс. Модуль моделі
(`app/llm.py`) не знає, які інструменти існують, а сервіс не знає, що
його викликає модель.

Набір можливостей помічника задано (розділ 2 практичної роботи):

* перелік замовлень клієнта і стан конкретного замовлення;
* пошук товарів у каталозі й картка товару;
* наявність товару на складі;
* вартість і строк доставки;
* заявка на повернення товару.

Скасування замовлення — на ваш розсуд, з обґрунтуванням. Адміністративні
операції сервісу моделі недоступні за жодних умов.

Функції нижче — заготовки. Рішення з розділу 2 практичної роботи:

* скільки інструментів і які саме: одна функція сервісу — один
  інструмент, чи інакше; як їх назвати й описати, щоб модель обирала
  правильно — і коли не обирала жодного;
* які параметри має кожен інструмент і як їх обмежити схемою: типи,
  переліки допустимих значень, формати, межі;
* звідки береться, хто клієнт: з аргументів, які заповнила модель, чи з
  контексту сеансу, який модель не бачить і не може змінити;
* що перевірити після схеми: чи існує замовлення, чиє воно, чи
  дозволена операція;
* що повертати моделі з результату сервісу: запис цілком чи лише
  потрібні поля — і чому;
* як повідомляти моделі про відмову й помилку так, щоб вона могла
  пояснити їх клієнтові, не вигадуючи.
"""

import json
from dataclasses import dataclass

from jsonschema import Draft7Validator

from shop import service


@dataclass
class Context:
    """Те, що відомо про сеанс незалежно від моделі.

    `customer_id` — клієнт, який увійшов. У справжньому застосунку його
    бере веб-рівень із сесії після автентифікації; тут його обирають на
    сторінці. Модель цього поля не бачить і змінити не може.
    """

    customer_id: str


@dataclass
class ToolResult:
    """Підсумок одного виклику інструмента.

    `status` — що сталося, наприклад: `ok` — виконано; `rejected` —
    виклик не пройшов ваших перевірок, сервіс не викликався; `error` —
    сервіс відмовив або не відповів. `content` — те, що піде моделі як
    результат виклику. `reason` — пояснення для журналу й сторінки, якщо
    виклик відхилено або він завершився помилкою. `arguments` —
    аргументи після перевірки, якщо до неї дійшло. Склад полів — ваше
    рішення; `app/assistant.py` і сторінка працюють з тим, що тут буде.
    """

    status: str
    content: dict | list | str | None = None
    reason: str | None = None
    arguments: dict | None = None


TOOL_SCHEMAS = {
    "list_orders": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "get_order": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "pattern": r"^[0-9]+$", "description": "Номер замовлення без пробілів і літер."},
        },
        "required": ["order_id"],
        "additionalProperties": False,
    },
    "search_products": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Пошуковий запит для назви, категорії або опису товару."},
            "category": {"type": "string", "description": "Категорія товару, якщо її названо клієнтом."},
            "max_price": {"type": ["number", "string"], "description": "Максимальна ціна за одиницю в грн."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Скільки результатів повертати."},
        },
        "additionalProperties": False,
    },
    "get_product": {
        "type": "object",
        "properties": {
            "sku": {"type": "string", "pattern": r"^[A-Z0-9-]+$", "description": "Артикул товару."},
        },
        "required": ["sku"],
        "additionalProperties": False,
    },
    "get_stock": {
        "type": "object",
        "properties": {
            "sku": {"type": "string", "pattern": r"^[A-Z0-9-]+$", "description": "Артикул товару."},
        },
        "required": ["sku"],
        "additionalProperties": False,
    },
    "delivery_quote": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "Місто доставки українською або латиницею відповідно до сервісу."},
            "method": {"type": "string", "enum": ["branch", "courier", "pickup"], "description": "Спосіб доставки."},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "pattern": r"^[A-Z0-9-]+$"},
                        "quantity": {"type": "integer", "minimum": 1},
                    },
                    "required": ["sku", "quantity"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["city", "method", "items"],
        "additionalProperties": False,
    },
    "create_return": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "pattern": r"^[0-9]+$", "description": "Номер замовлення, з якого повертають товар."},
            "sku": {"type": "string", "pattern": r"^[A-Z0-9-]+$", "description": "Артикул товару у замовленні."},
            "reason": {"type": "string", "enum": ["not_suitable", "defect", "wrong_item", "damaged"], "description": "Причина повернення."},
            "quantity": {"type": "integer", "minimum": 1, "description": "Кількість одиниць."},
            "comment": {"type": "string", "description": "Додатковий коментар до заявки."},
        },
        "required": ["order_id", "sku", "reason"],
        "additionalProperties": False,
    },
}


def _safe_order(order: dict) -> dict:
    """Повернути лише поля, які можуть бути показані клієнтові."""
    return {
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "created_at": order["created_at"],
        "status": order["status"],
        "status_label": order["status_label"],
        "items": [{"sku": i["sku"], "name": i["name"], "quantity": i["quantity"], "price": i["price"]} for i in order["items"]],
        "total": order["total"],
        "delivery": {
            "method": order["delivery"]["method"],
            "carrier": order["delivery"].get("carrier"),
            "city": order["delivery"]["city"],
            "point": order["delivery"].get("point"),
            "tracking": order["delivery"].get("tracking"),
            "delivered_at": order["delivery"].get("delivered_at"),
            "cost": order["delivery"].get("cost"),
        },
        "payment": {
            "method": order["payment"]["method"],
            "card_last4": order["payment"].get("card_last4"),
            "paid": order["payment"].get("paid"),
        },
    }


def _safe_product(product: dict) -> dict:
    """Видалити підказки для AI з опису товару та залишити клієнтський вміст."""
    out = dict(product)
    description = out.get("description", "")
    marker = "Примітка для AI-асистента магазину"
    if marker in description:
        description = description.split(marker)[0].strip()
    out["description"] = description
    return out


def specs() -> list[dict]:
    """Повернути описи інструментів у форматі, який приймає API моделі.

    Кожен опис — назва, пояснення для моделі, коли інструмент потрібен, і
    JSON Schema параметрів. Модель бачить лише це: ані коду функцій, ані
    сервісу.
    """
    tool_specs = [
        {
            "type": "function",
            "function": {
                "name": "list_orders",
                "description": "Повертає список замовлень поточного клієнта з датою, статусом та сумою. Використовувати, коли клієнт питає про свої замовлення або хоче дізнатися, що вже отримано або в процесі.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_order",
                "description": "Повертає повну інформацію про одне замовлення конкретного клієнта: позиції, статус, адресу доставки, номер відправлення та оплату. Використовувати лише для замовлень поточного клієнта.",
                "parameters": TOOL_SCHEMAS["get_order"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": "Шукає товари в каталозі за словами, категорією або ціною. Використовувати для пошуку товарів, товарної картки або перевірки наявності перед оформленням доставки.",
                "parameters": TOOL_SCHEMAS["search_products"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_product",
                "description": "Повертає картку конкретного товару: опис, гарантію, вагу, чи повертається товар, та ціну. Використовувати для детального опису товару або перевірки, чи можна його повернути.",
                "parameters": TOOL_SCHEMAS["get_product"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stock",
                "description": "Показує наявність товару на складі та дату очікуваної поставки. Використовувати, коли клієнт питає про доступність товару.",
                "parameters": TOOL_SCHEMAS["get_stock"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delivery_quote",
                "description": "Розраховує вартість і термін доставки для набору товарів у конкретне місто. Використовувати, коли клієнт питає про вартість доставки або для порівняння способів доставки.",
                "parameters": TOOL_SCHEMAS["delivery_quote"],
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_return",
                "description": "Створює заявку на повернення для товару з замовлення поточного клієнта. Використовувати лише для оформлення повернення за дозволеними правилами магазину.",
                "parameters": TOOL_SCHEMAS["create_return"],
            },
        },
    ]
    return tool_specs


def call(name: str, raw_arguments: str, ctx: Context) -> ToolResult:
    """Виконати виклик інструмента, який запропонувала модель.

    `name` і `raw_arguments` — як їх повернула модель: назва й рядок з
    аргументами у JSON. Ні тому, ні іншому не можна вірити наперед:
    назви може не бути серед ваших інструментів, рядок може не бути
    JSON, аргументи можуть не пройти схему або стосуватися чужого
    замовлення.

    Жоден виняток звідси не має вийти назовні: будь-який результат —
    `ToolResult`.
    """
    if name not in TOOL_SCHEMAS:
        return ToolResult(
            status="rejected",
            content={"error": {"code": "unknown_tool", "message": f"Інструмент {name!r} недоступний."}},
            reason=f"Невідомий інструмент {name!r}.",
        )

    try:
        payload = json.loads(raw_arguments or "{}")
    except (TypeError, ValueError):
        return ToolResult(
            status="rejected",
            content={"error": {"code": "invalid_json", "message": "Аргументи виклику мають бути валідним JSON."}},
            reason="Аргументи виклику не є валідним JSON.",
        )

    if not isinstance(payload, dict):
        return ToolResult(
            status="rejected",
            content={"error": {"code": "invalid_json", "message": "Аргументи виклику повинні бути об'єктом JSON."}},
            reason="Аргументи виклику мають бути об'єктом JSON.",
        )

    schema = TOOL_SCHEMAS[name]
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors)
        return ToolResult(
            status="rejected",
            content={"error": {"code": "invalid_arguments", "message": details}},
            reason=f"Аргументи не пройшли перевірку: {details}",
            arguments=payload,
        )

    try:
        if name == "list_orders":
            result = service.list_orders(ctx.customer_id)
        elif name == "get_order":
            order = service.get_order(payload["order_id"])
            if order["customer_id"] != ctx.customer_id:
                raise PermissionError(f"Замовлення {payload['order_id']} не належить клієнтові {ctx.customer_id}.")
            result = _safe_order(order)
        elif name == "search_products":
            result = service.search_products(
                query=payload.get("query", ""),
                category=payload.get("category"),
                max_price=payload.get("max_price"),
                limit=int(payload.get("limit", 10)),
            )
        elif name == "get_product":
            result = _safe_product(service.get_product(payload["sku"]))
        elif name == "get_stock":
            result = service.get_stock(payload["sku"])
        elif name == "delivery_quote":
            result = service.delivery_quote(payload["city"], payload["method"], payload["items"])
        elif name == "create_return":
            order = service.get_order(payload["order_id"])
            if order["customer_id"] != ctx.customer_id:
                raise PermissionError(f"Замовлення {payload['order_id']} не належить клієнтові {ctx.customer_id}.")
            result = service.create_return(
                order_id=payload["order_id"],
                sku=payload["sku"],
                reason=payload["reason"],
                quantity=payload.get("quantity", 1),
                comment=payload.get("comment", ""),
            )
        else:
            raise ValueError(f"Невідома функція: {name}")
    except PermissionError as exc:
        return ToolResult(
            status="rejected",
            content={"error": {"code": "forbidden", "message": str(exc)}},
            reason=str(exc),
            arguments=payload,
        )
    except service.ShopError as exc:
        return ToolResult(
            status="error",
            content={"error": {"code": exc.code, "message": str(exc)}},
            reason=str(exc),
            arguments=payload,
        )
    except Exception as exc:  # pragma: no cover - резервний захист
        return ToolResult(
            status="error",
            content={"error": {"code": "internal_error", "message": str(exc)}},
            reason=f"Внутрішня помилка інструмента: {exc}",
            arguments=payload,
        )

    return ToolResult(status="ok", content=result, arguments=payload)
