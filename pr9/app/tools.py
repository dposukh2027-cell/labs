import json
from dataclasses import dataclass

from jsonschema import Draft7Validator

from shop import service


@dataclass
class Context:
    customer_id: str


@dataclass
class ToolResult:
    status: str
    content: dict | list | str | None = None
    reason: str | None = None
    arguments: dict | None = None


def _validate_args(name: str, args: dict) -> list[str]:
    specs = {
        "list_orders": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "get_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"], "additionalProperties": False},
        "search_products": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": ["string", "null"]}, "max_price": {"type": ["string", "number", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["query"], "additionalProperties": False},
        "get_product": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"], "additionalProperties": False},
        "get_stock": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"], "additionalProperties": False},
        "delivery_quote": {"type": "object", "properties": {"city": {"type": "string"}, "method": {"type": "string", "enum": ["branch", "courier", "pickup"]}, "items": {"type": "array", "items": {"type": "object", "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}}, "required": ["sku", "quantity"], "additionalProperties": False}}}, "required": ["city", "method", "items"], "additionalProperties": False},
        "create_return": {"type": "object", "properties": {"order_id": {"type": "string"}, "sku": {"type": "string"}, "reason": {"type": "string", "enum": ["not_suitable", "defect", "wrong_item", "damaged"]}, "quantity": {"type": "integer", "minimum": 1}, "comment": {"type": "string"}}, "required": ["order_id", "sku", "reason"], "additionalProperties": False},
        "cancel_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"], "additionalProperties": False},
        "list_returns": {"type": "object", "properties": {"order_id": {"type": ["string", "null"]}}, "required": [], "additionalProperties": False},
    }
    schema = specs.get(name)
    if schema is None:
        return [f"невідомий інструмент {name!r}"]
    errors = sorted(Draft7Validator(schema).iter_errors(args), key=lambda e: list(e.path))
    return [f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


def specs() -> list[dict]:
    """Повернути описи інструментів у форматі, який приймає API моделі."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_orders",
                "description": "Повертає замовлення поточного клієнта від нових до старих.",
                "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_order",
                "description": "Повертає повні дані про конкретне замовлення клієнта.",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_products",
                "description": "Шукає товари у каталозі за словами, категорією та ціною.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": ["string", "null"]}, "max_price": {"type": ["string", "number", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["query"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_product",
                "description": "Повертає картку товару за артикулом.",
                "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stock",
                "description": "Повертає наявність товару на складі.",
                "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delivery_quote",
                "description": "Розраховує вартість і строк доставки набору товарів в місто.",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "method": {"type": "string", "enum": ["branch", "courier", "pickup"]}, "items": {"type": "array", "items": {"type": "object", "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1}}, "required": ["sku", "quantity"], "additionalProperties": False}}}, "required": ["city", "method", "items"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_return",
                "description": "Створює заявку на повернення товару з замовлення.",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}, "sku": {"type": "string"}, "reason": {"type": "string", "enum": ["not_suitable", "defect", "wrong_item", "damaged"]}, "quantity": {"type": "integer", "minimum": 1}, "comment": {"type": "string"}}, "required": ["order_id", "sku", "reason"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_order",
                "description": "Скасовує замовлення, якщо воно ще в статусі готується.",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"], "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_returns",
                "description": "Повертає створені заявки на повернення для замовлення або всіх замовлень.",
                "parameters": {"type": "object", "properties": {"order_id": {"type": ["string", "null"]}}, "required": [], "additionalProperties": False},
            },
        },
    ]


def call(name: str, raw_arguments: str | dict, ctx: Context) -> ToolResult:
    """Виконати виклик інструмента, який запропонувала модель."""
    if not isinstance(raw_arguments, (str, dict)):
        return ToolResult("rejected", None, "Аргументи інструмента мають бути JSON або словником", {})

    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        return ToolResult("rejected", None, "Аргументи не є валідним JSON", {})
    if not isinstance(arguments, dict):
        return ToolResult("rejected", None, "Аргументи повинні бути JSON-об'єктом", {})

    errors = _validate_args(name, arguments)
    if errors:
        return ToolResult("rejected", None, "Аргументи інструмента не пройшли перевірку: " + "; ".join(errors), arguments)

    try:
        if name == "list_orders":
            content = service.list_orders(ctx.customer_id)
        elif name == "get_order":
            order = service.get_order(str(arguments["order_id"]))
            if str(order.get("customer_id")) != str(ctx.customer_id):
                raise service.PolicyViolation("це замовлення належить іншому клієнтові")
            content = order
        elif name == "search_products":
            content = service.search_products(
                query=str(arguments.get("query", "")),
                category=arguments.get("category"),
                max_price=arguments.get("max_price"),
                limit=int(arguments.get("limit", 10)),
            )
        elif name == "get_product":
            content = service.get_product(str(arguments["sku"]))
        elif name == "get_stock":
            content = service.get_stock(str(arguments["sku"]))
        elif name == "delivery_quote":
            content = service.delivery_quote(str(arguments["city"]), str(arguments["method"]), arguments["items"])
        elif name == "create_return":
            order_id = str(arguments["order_id"])
            order = service.get_order(order_id)
            if str(order.get("customer_id")) != str(ctx.customer_id):
                raise service.PolicyViolation("заявку на повернення не можна оформити для чужого замовлення")
            content = service.create_return(
                order_id,
                str(arguments["sku"]),
                str(arguments["reason"]),
                int(arguments.get("quantity", 1)),
                str(arguments.get("comment", "")),
            )
        elif name == "cancel_order":
            order_id = str(arguments["order_id"])
            order = service.get_order(order_id)
            if str(order.get("customer_id")) != str(ctx.customer_id):
                raise service.PolicyViolation("скасувати можна лише власне замовлення")
            content = service.cancel_order(order_id)
        elif name == "list_returns":
            order_id = arguments.get("order_id")
            if order_id is not None:
                order = service.get_order(str(order_id))
                if str(order.get("customer_id")) != str(ctx.customer_id):
                    raise service.PolicyViolation("ви не можете переглядати чужі заявки на повернення")
            content = service.list_returns(str(order_id) if order_id is not None else None)
        else:
            return ToolResult("rejected", None, f"інструмент {name!r} не реалізований", arguments)
    except service.ShopError as exc:
        return ToolResult("error", None, str(exc), arguments)
    except Exception as exc:  # noqa: BLE001
        return ToolResult("error", None, f"внутрішня помилка інструмента: {exc}", arguments)

    return ToolResult("ok", content=content, reason="виконано", arguments=arguments)
