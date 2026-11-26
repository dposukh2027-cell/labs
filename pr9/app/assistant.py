import json
import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from shop import service

from . import llm
from .tools import Context, call, specs

load_dotenv()

MAX_ROUNDS = int(os.getenv("TOOL_MAX_ROUNDS", "3"))


@dataclass
class ToolTrace:
    round: int
    name: str
    arguments: str
    status: str
    reason: str | None = None
    result: dict | list | str | None = None
    elapsed: float | None = None


@dataclass
class Answer:
    text: str
    calls: list[ToolTrace] = field(default_factory=list)
    rounds: int = 0
    stopped: str = "answer"
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None


def _fallback_answer(question: str, customer_id: str) -> Answer:
    order_id = None
    if match := re.search(r"(?:замовлення|order|№)\s*[:#-]?\s*(\d+)", question, flags=re.IGNORECASE):
        order_id = match.group(1)
    low = question.lower()
    if "повернути" in low or "повернення" in low:
        text = "Я можу допомогти з поверненням, але для точного оформлення потрібно підтвердити номер замовлення та товар."
    elif "скасувати" in low or "скасування" in low:
        text = "Я можу перевірити, чи можна скасувати замовлення, якщо вкажете номер замовлення."
    elif "стан" in low or "відстеж" in low:
        text = "Перевірю статус замовлення за номером."
    else:
        text = "Можу допомогти з питанням про замовлення, поверненням або скасуванням. Вкажіть номер замовлення і, якщо потрібно, товар."
    if order_id:
        try:
            order = service.get_order(order_id)
            if str(order.get("customer_id")) != str(customer_id):
                text = "Це замовлення належить іншому клієнтові, тому обробку треба передати оператору."
            else:
                text = f"Замовлення {order_id} зараз має статус {service.ORDER_STATUSES.get(order['status'], order['status'])}."
        except service.ShopError:
            text = f"Замовлення {order_id} не знайдено або недоступне для перегляду."
    return Answer(text=text, calls=[], rounds=0, stopped="fallback", model=None, elapsed={"model": 0.0, "tools": 0.0}, usage={})


def answer(question: str, customer_id: str) -> Answer:
    """Відповісти клієнтові, за потреби викликаючи інструменти."""
    if not os.getenv("LLM_API_KEY"):
        return _fallback_answer(question, customer_id)

    messages = llm.build_messages(question)
    ctx = Context(customer_id)
    traces: list[ToolTrace] = []
    total_model = 0.0
    total_tools = 0.0
    tool_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for round_no in range(1, MAX_ROUNDS + 1):
        try:
            response = llm.chat(messages, specs(), tool_choice="auto")
        except llm.LLMError as exc:
            return Answer(
                text=f"Не вдалося звернутися до моделі: {exc}",
                calls=traces,
                rounds=round_no - 1,
                stopped="error",
                model=None,
                elapsed={"model": round(total_model, 3), "tools": round(total_tools, 3)},
                usage=tool_usage,
            )

        total_model += float(response.get("elapsed", 0.0))
        usage = response.get("usage") or {}
        tool_usage["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        tool_usage["completion_tokens"] += int(usage.get("completion_tokens", 0))
        tool_usage["total_tokens"] += int(usage.get("total_tokens", 0))

        tool_calls = response.get("tool_calls") or []
        if tool_calls:
            for tool_call in tool_calls:
                name = (tool_call.get("function") or {}).get("name")
                raw_arguments = (tool_call.get("function") or {}).get("arguments") or "{}"
                start = time.time()
                result = call(name, raw_arguments, ctx)
                elapsed = time.time() - start
                total_tools += elapsed
                traces.append(
                    ToolTrace(
                        round=round_no,
                        name=name or "unknown",
                        arguments=str(raw_arguments),
                        status=result.status,
                        reason=result.reason,
                        result=result.content,
                        elapsed=round(elapsed, 3),
                    )
                )
                messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": tool_call.get("id"),
                    "type": "function",
                    "function": {"name": name, "arguments": str(raw_arguments)},
                }]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "name": name,
                    "content": json.dumps({
                        "status": result.status,
                        "reason": result.reason,
                        "content": result.content,
                    }, ensure_ascii=False),
                })
            continue

        content = (response.get("content") or "").strip()
        if content:
            return Answer(
                text=content,
                calls=traces,
                rounds=round_no,
                stopped="answer",
                model=response.get("model"),
                elapsed={"model": round(total_model, 3), "tools": round(total_tools, 3)},
                usage=tool_usage,
            )

    return Answer(
        text="Модель не змогла дати текстову відповідь у межах ліміту звертань.",
        calls=traces,
        rounds=MAX_ROUNDS,
        stopped="limit",
        model=None,
        elapsed={"model": round(total_model, 3), "tools": round(total_tools, 3)},
        usage=tool_usage,
    )
