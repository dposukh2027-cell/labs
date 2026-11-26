"""Цикл помічника: від питання клієнта до відповіді, спертої на дані
магазину.

Єдине місце, яке знає послідовність: спитати модель з описами
інструментів (`llm.chat`), виконати виклики, які вона запропонувала
(`tools.call`), повернути їй результати і спитати ще раз — доки вона не
відповість текстом або доки не вичерпано обмеження. Учасники одне про
одного не знають: модель — про сервіс магазину, інструменти — про API
моделі, веб-рівень — ні про що з цього.

Функція `answer` — заготовка. Рішення з розділу 2 практичної роботи:

* скільки разів можна повернутися до моделі і що робити, коли ліміт
  вичерпано, а відповіді текстом так і немає;
* що робити, якщо модель запропонувала кілька викликів одразу: виконати
  всі, частину, жодного? Чи залежить це від того, що саме вони роблять?
* як звʼязати результат із викликом, до якого він належить;
* що потрапляє в журнал викликів (`ToolTrace`) і що з нього показувати
  на сторінці;
* що рахувати окремо: час моделі й час інструментів — це різні витрати.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from . import llm, tools
from shop import service

load_dotenv()

# Скільки разів можна звернутися до моделі за одне питання клієнта.
MAX_ROUNDS = int(os.getenv("TOOL_MAX_ROUNDS", "3"))
MOCK_FALLBACK = os.getenv("LLM_MOCK_FALLBACK", "true").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ToolTrace:
    """Запис про один виклик інструмента — для сторінки й для перевірки.

    `round` — на якому звертанні до моделі його запропоновано (з 1).
    `name` і `arguments` — як їх повернула модель, до будь-яких
    перевірок. `status` і `reason` — що з викликом зробив ваш код.
    `result` — що повернулося моделі. `elapsed` — час виконання, секунди.
    """

    round: int
    name: str
    arguments: str
    status: str
    reason: str | None = None
    result: dict | list | str | None = None
    elapsed: float | None = None


@dataclass
class Answer:
    """Результат циклу — те, з чим працює веб-рівень.

    `text` — відповідь клієнтові. `calls` — журнал викликів інструментів
    у порядку виконання. `rounds` — скільки разів звертались до моделі.
    `stopped` — чому цикл завершився, наприклад `answer` (модель
    відповіла текстом) чи `limit` (вичерпано обмеження). `elapsed` — час
    за видами, наприклад `{"model": 3.4, "tools": 0.02}`. `usage` —
    токени запиту й відповіді, сумарно за всі звертання.
    """

    text: str
    calls: list[ToolTrace] = field(default_factory=list)
    rounds: int = 0
    stopped: str = "answer"
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None


def _merge_usage(base: dict | None, extra: dict | None) -> dict:
    if base is None:
        base = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for key in base:
        base[key] = int(base[key]) + int((extra or {}).get(key, 0))
    return base


def _local_demo_answer(question: str, customer_id: str) -> Answer:
    """Provide safe, deterministic shop lookups when the remote LLM is unavailable."""
    question_lower = question.casefold()
    traces: list[ToolTrace] = []
    tool_seconds = 0.0
    context = tools.Context(customer_id=customer_id)

    def invoke(name: str, arguments: dict, round_number: int = 1):
        nonlocal tool_seconds
        raw_arguments = json.dumps(arguments, ensure_ascii=False)
        started = time.perf_counter()
        result = tools.call(name, raw_arguments, context)
        elapsed = time.perf_counter() - started
        tool_seconds += elapsed
        traces.append(ToolTrace(
            round=round_number,
            name=name,
            arguments=raw_arguments,
            status=result.status,
            reason=result.reason,
            result=result.content,
            elapsed=elapsed,
        ))
        return result

    def done(text: str) -> Answer:
        return Answer(
            text=f"Локальний демо-режим (без AI): {text}",
            calls=traces,
            rounds=1 if traces else 0,
            stopped="answer",
            model="local-demo",
            elapsed={"model": 0.0, "tools": round(tool_seconds, 3)},
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    if any(term in question_lower for term in ("поверніть гроші", "повернути гроші", "змініть ціну", "нарахуйте бонус", "змініть статус")):
        return done("не можу виконувати повернення коштів, змінювати ціни чи статуси або нараховувати бонуси. Це демонстраційний режим.")

    order_id = re.search(r"\b\d{5}\b", question)
    if order_id and any(term in question_lower for term in ("замов", "статус", "посил", "відправ", "достав")):
        result = invoke("get_order", {"order_id": order_id.group()})
        if result.status != "ok":
            error = (result.content or {}).get("error", {})
            return done(error.get("message", "Не вдалося отримати це замовлення."))
        order = result.content
        items = ", ".join(f"{item['name']} — {item['quantity']} шт." for item in order["items"])
        details = [f"Замовлення №{order['order_id']}: {order['status_label']}.", f"Склад: {items}.", f"Сума: {order['total']} грн."]
        if order["delivery"].get("tracking"):
            details.append(f"Номер відправлення: {order['delivery']['tracking']}.")
        if order["delivery"].get("delivered_at"):
            details.append(f"Дата отримання: {order['delivery']['delivered_at']}.")
        return done(" ".join(details))

    if any(term in question_lower for term in ("мої замовлення", "список замовлень", "покажіть замовлення", "покажи замовлення", "мої покупки")):
        result = invoke("list_orders", {})
        if result.status != "ok":
            error = (result.content or {}).get("error", {})
            return done(error.get("message", "Не вдалося отримати список замовлень."))
        orders = result.content
        if not orders:
            return done("у вас поки немає замовлень.")
        lines = [f"№{order['order_id']} — {order['status_label']}, {order['total']} грн." for order in orders]
        return done("Ваші замовлення: " + " ".join(lines))

    if any(term in question_lower for term in ("повер", "скасу", "відмін")):
        return done("у локальному демо-режимі доступні лише перевірки замовлень, товарів, наявності та доставки. Жодної зміни не виконано.")

    product_question = any(term in question_lower for term in (
        "товар", "роутер", "навушник", "пилосос", "телевізор", "годинник",
        "кабель", "павербанк", "наявн", "скільки коштує", "достав",
        "ціна", "опис",
    ))
    if product_question:
        result = invoke("search_products", {"query": "", "limit": 50})
        if result.status != "ok":
            error = (result.content or {}).get("error", {})
            return done(error.get("message", "Не вдалося знайти товари."))

        ignored = {"чи", "є", "в", "у", "на", "і", "й", "а", "з", "за", "для", "про", "товар", "товару", "наявності", "наявність", "зараз", "скільки", "коштує", "ціна", "опис", "доставка", "доставки", "будь", "ласка"}
        query_words = set(re.findall(r"[a-zа-яіїєґ0-9]+", question_lower)) - ignored
        candidates = []
        for product in result.content:
            name_words = set(re.findall(r"[a-zа-яіїєґ0-9]+", product["name"].casefold()))
            sku_words = set(re.findall(r"[a-z0-9]+", product["sku"].casefold()))
            score = len(query_words & (name_words | sku_words))
            if score:
                candidates.append((score, product))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
            return done("не зміг однозначно визначити товар. Напишіть його точну назву або артикул.")

        product = candidates[0][1]
        wants_stock = any(term in question_lower for term in ("наявн", "є зараз", "є в наявності", "скільки є", "залиш"))
        wants_details = any(term in question_lower for term in ("опис", "характерист", "розкаж", "про товар"))
        wants_delivery = any(term in question_lower for term in ("достав", "вартість доставки", "скільки коштує доставка"))
        parts = [f"{product['name']} — {product['price']} грн."]

        if wants_details:
            detail_result = invoke("get_product", {"sku": product["sku"]}, 2)
            if detail_result.status == "ok":
                details = detail_result.content
                parts.append(f"{details['description']} Гарантія: {details['warranty_months']} міс.")
            else:
                error = (detail_result.content or {}).get("error", {})
                parts.append(error.get("message", "Картка товару недоступна."))

        if wants_stock:
            stock_result = invoke("get_stock", {"sku": product["sku"]}, 2)
            if stock_result.status == "ok":
                stock = stock_result.content
                stock_text = f"У наявності: {stock['available']} шт."
                if stock.get("expected_restock"):
                    stock_text += f" Очікувана поставка: {stock['expected_restock']}."
                parts.append(stock_text)
            else:
                error = (stock_result.content or {}).get("error", {})
                parts.append(error.get("message", "Не вдалося перевірити наявність."))

        if wants_delivery:
            cities = (
                "Кременчук", "Івано-Франківськ", "Запоріжжя", "Чернігів",
                "Київ", "Львів", "Харків", "Одеса", "Дніпро", "Вінниця",
                "Полтава", "Черкаси", "Житомир", "Рівне", "Тернопіль",
                "Ужгород", "Суми", "Миколаїв",
            )
            city_variants = {
                "Київ": ("київ", "києві", "києва"),
                "Львів": ("львів", "львові", "львова"),
                "Харків": ("харків", "харкові"),
                "Одеса": ("одеса", "одесі", "одесу"),
                "Дніпро": ("дніпро", "дніпрі"),
                "Запоріжжя": ("запоріжжя", "запоріжжі"),
                "Вінниця": ("вінниця", "вінниці", "вінницю"),
                "Полтава": ("полтава", "полтаві", "полтаву"),
                "Кременчук": ("кременчук", "кременчуці", "кременчука"),
                "Черкаси": ("черкаси", "черкасах"),
                "Житомир": ("житомир", "житомирі"),
                "Рівне": ("рівне", "рівному"),
                "Івано-Франківськ": ("івано-франківськ", "івано-франківську"),
                "Тернопіль": ("тернопіль", "тернополі"),
                "Ужгород": ("ужгород", "ужгороді"),
                "Чернігів": ("чернігів", "чернігові"),
                "Суми": ("суми", "сумах"),
                "Миколаїв": ("миколаїв", "миколаєві"),
            }
            city = next(
                (name for name in cities
                 if any(variant in question_lower for variant in city_variants.get(name, (name.casefold(),)))),
                None,
            )
            if not city:
                parts.append("Щоб порахувати доставку, вкажіть місто.")
            else:
                method = "courier" if "кур" in question_lower else ("pickup" if any(word in question_lower for word in ("самовив", "самовивіз")) else "branch")
                quote_result = invoke("delivery_quote", {
                    "city": city,
                    "method": method,
                    "items": [{"sku": product["sku"], "quantity": 1}],
                }, 2)
                if quote_result.status == "ok":
                    quote = quote_result.content
                    parts.append(f"Доставка: {quote['cost']} грн., {quote['days']}.")
                else:
                    error = (quote_result.content or {}).get("error", {})
                    parts.append(error.get("message", "Не вдалося розрахувати доставку."))
        return done(" ".join(parts))

    return done("можу перевірити статус і список замовлень, знайти товар, дізнатися наявність або порахувати доставку. Напишіть, наприклад: «Де моє замовлення 10458?»")


def answer(question: str, customer_id: str) -> Answer:
    """Відповісти клієнтові, за потреби викликаючи інструменти.

    `customer_id` — клієнт, який увійшов; його передає веб-рівень, а не
    модель.
    """
    if not isinstance(question, str) or not question.strip():
        return Answer(text="Порожнє питання. Напишіть, що саме треба перевірити.", calls=[], rounds=0, stopped="error", elapsed={"model": 0.0, "tools": 0.0}, usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    messages = llm.build_messages(question.strip())
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    total_model_time = 0.0
    total_tool_time = 0.0
    traces: list[ToolTrace] = []
    ctx = tools.Context(customer_id=customer_id)

    for round_index in range(1, MAX_ROUNDS + 1):
        try:
            response = llm.chat(messages, tools.specs(), tool_choice="auto")
        except llm.LLMError as exc:
            if MOCK_FALLBACK:
                return _local_demo_answer(question.strip(), customer_id)
            return Answer(
                text=f"Не вдалося отримати відповідь від моделі: {exc}",
                calls=traces,
                rounds=round_index - 1,
                stopped="error",
                model=None,
                elapsed={"model": round(total_model_time, 3), "tools": round(total_tool_time, 3)},
                usage=usage,
            )

        total_model_time += float(response.get("elapsed", 0.0) or 0.0)
        usage = _merge_usage(usage, response.get("usage") or {})

        if response.get("content") and not response.get("tool_calls"):
            return Answer(
                text=response["content"].strip(),
                calls=traces,
                rounds=round_index,
                stopped="answer",
                model=response.get("model"),
                elapsed={"model": round(total_model_time, 3), "tools": round(total_tool_time, 3)},
                usage=usage,
            )

        if not response.get("tool_calls"):
            return Answer(
                text="Не вдалося сформувати відповідь на основі доступних даних. Спробуйте уточнити питання.",
                calls=traces,
                rounds=round_index,
                stopped="answer",
                model=response.get("model"),
                elapsed={"model": round(total_model_time, 3), "tools": round(total_tool_time, 3)},
                usage=usage,
            )

        if response.get("assistant_message"):
            messages.append(response["assistant_message"])

        for call in response["tool_calls"]:
            call_id = call.get("id") or f"call_{time.time_ns()}"
            call_name = call.get("name") or "unknown_tool"
            raw_args = call.get("arguments") or "{}"
            start = time.perf_counter()
            result = tools.call(call_name, raw_args, ctx)
            elapsed = time.perf_counter() - start
            total_tool_time += elapsed
            trace = ToolTrace(
                round=round_index,
                name=call_name,
                arguments=str(raw_args),
                status=result.status,
                reason=result.reason,
                result=result.content,
                elapsed=elapsed,
            )
            traces.append(trace)
            messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result.content, ensure_ascii=False)})

        if round_index >= MAX_ROUNDS:
            break

    return Answer(
        text="Не вдалося знайти достатньо даних у доступних інструментах, щоб дати точну відповідь. Спробуйте сформулювати питання коротше або уточніть, що саме потрібно перевірити.",
        calls=traces,
        rounds=MAX_ROUNDS,
        stopped="limit",
        model=llm.MODEL,
        elapsed={"model": round(total_model_time, 3), "tools": round(total_tool_time, 3)},
        usage=usage,
    )
