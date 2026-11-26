"""Workflow обробки звернення клієнта: кроки, переходи, обмеження.

Єдине місце, яке знає послідовність. Тут вирішується, який крок іде
наступним, з якими даними і що робити з його результатом. Модель
(`app/llm.py`) виконує окремі кроки й не знає, що буде далі.
Інструменти (`app/tools.py`) виконують виклики й не знають, хто їх
просить — модель чи цей модуль. Сховище (`app/store.py`) зберігає
стан (`app/state.py`) і не знає, що в ньому. Веб-рівень бачить лише
`start`, `resume` і `Run`.

Звернення не обробляється за один виклик. `start` веде його, доки це
можливо без людини: до кінцевого стану або до паузи на підтвердження
оператором. `resume` продовжує після рішення оператора — можливо, за
годину й після перезапуску застосунку, тож усе потрібне для
продовження має бути в збереженому стані, а не в памʼяті процесу.

Функції нижче — заготовки. Рішення з розділу 2 практичної роботи:

* які кроки, у якому порядку, якого типу кожен (модель, інструмент,
  код, людина) і за якими умовами переходити між ними; де модель
  можна прибрати, бо код упорається сам;
* які статуси має звернення і які переходи між ними дозволені;
  кінцеві статуси — які саме, і чи в кожен веде хоч одна гілка;
* що передається між кроками (`Run.data`) і що з цього потрібно після
  паузи;
* які інструменти доступні кожному кроку і як це перевіряє код;
* як дія зі змінами виконується рівно один раз: подвійне підтвердження,
  повторне звернення, перезапуск між виконанням і записом стану;
* що перевірити ще раз після підтвердження, перш ніж виконувати;
* як рахуються обмеження — кроки, час автоматичної частини, токени — і
  що відбувається, коли якесь вичерпано посеред сценарію;
* як перевіряється відповідь клієнтові і що робити, якщо вона не
  пройшла перевірку.
"""

import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

from shop import service

from . import llm, store
from .schema import request_schema, validate
from .state import Run, Step

load_dotenv()

MAX_STEPS = int(os.getenv("WORKFLOW_MAX_STEPS", "12"))
TIMEOUT = float(os.getenv("WORKFLOW_TIMEOUT", "60"))
TOKEN_BUDGET = int(os.getenv("WORKFLOW_TOKEN_BUDGET", "8000"))


def limits() -> dict:
    """Обмеження одного звернення — для сторінки."""
    return {"max_steps": MAX_STEPS, "timeout": TIMEOUT, "token_budget": TOKEN_BUDGET}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step(run: Run, name: str, kind: str, status: str, detail: str,
          input_value=None, output_value=None, elapsed: float | None = None,
          usage: dict | None = None) -> None:
    run.steps.append(
        Step(
            n=len(run.steps) + 1,
            name=name,
            kind=kind,
            status=status,
            detail=detail,
            input=input_value,
            output=output_value,
            elapsed=elapsed,
            usage=usage,
            at=_now_iso(),
        )
    )
    run.updated_at = _now_iso()


def _infer_reason(text: str) -> str | None:
    low = text.lower()
    if any(word in low for word in ["не підійшов", "не подобається", "не підходить", "не тот"]):
        return "not_suitable"
    if any(word in low for word in ["дефект", "брак", "ламається", "не працює", "зламав"]):
        return "defect"
    if any(word in low for word in ["не той", "не те", "чужий товар", "не той товар"]):
        return "wrong_item"
    if any(word in low for word in ["пошкоджено", "розбито", "пошкодження"]):
        return "damaged"
    return None


def _extract_order_id(text: str) -> str | None:
    match = re.search(r"(?:замовлення|order|№)\s*[:#-]?\s*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    numbers = re.findall(r"\b(\d{4,})\b", text)
    return numbers[0] if numbers else None


def _extract_item_name(text: str, order: dict) -> str | None:
    low = re.sub(r"[^\w\s\-]", " ", text.lower())
    for item in order.get("items", []):
        product_name = str(item.get("name", "")).lower()
        product_name_clean = re.sub(r"[^\w\s\-]", " ", product_name)
        if not product_name_clean:
            continue
        if product_name_clean in low:
            return item["name"]
        tokens = [w for w in product_name_clean.split() if len(w) > 2]
        if tokens and any(token in low for token in tokens):
            return item["name"]
    return None


def _match_item(order: dict, item_name: str | None) -> dict | None:
    if not item_name:
        if len(order.get("items", [])) == 1:
            return order["items"][0]
        return None
    lowered = item_name.lower()
    for item in order.get("items", []):
        if lowered in str(item.get("name", "")).lower():
            return item
    return None


def _parse_request(text: str) -> dict:
    if not text or not str(text).strip():
        raise ValueError("порожній текст звернення")
    cleaned = text.strip()
    try:
        payload = llm.complete([
            {"role": "system", "content": "Розбери звернення клієнта магазину. Якщо чогось не названо — null."},
            {"role": "user", "content": cleaned},
        ], schema=request_schema())
        raw = payload.get("text") or payload.get("parsed") or payload
        parsed = validate(raw)
        return parsed
    except (llm.LLMError, ValueError, TypeError):
        lower = cleaned.lower()
        kind = "other"
        if any(word in lower for word in ["повернути", "повернення", "поверну"]):
            kind = "return"
        elif any(word in lower for word in ["скасувати", "скасування", "анулювати", "відмінити"]):
            kind = "cancel"
        elif any(word in lower for word in ["стан", "статус", "дізнатися", "перевірити", "де моє замовлення", "коли прийде"]):
            kind = "status"
        order_id = _extract_order_id(cleaned)
        item = _extract_item_name(cleaned, {"items": []}) or None
        reason = _infer_reason(cleaned)
        return {
            "kind": kind,
            "order_id": order_id,
            "item": item,
            "reason": reason,
        }


def _status_message(order: dict) -> str:
    status_text = service.ORDER_STATUSES.get(order.get("status"), order.get("status"))
    return f"Статус замовлення {order['order_id']} — {status_text}."


def start(text: str, customer_id: str) -> Run:
    """Прийняти нове звернення й вести його, доки це можливо без людини."""
    if not text or not str(text).strip():
        raise ValueError("порожній текст звернення")
    try:
        service.get_customer(customer_id)
    except service.ShopError as exc:
        raise ValueError(f"невідомий клієнт: {exc}") from exc

    run = Run(
        run_id=f"R-{uuid4().hex[:8]}",
        customer_id=str(customer_id),
        text=str(text).strip(),
        status="running",
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    run.usage = {"model": 0, "tools": 0}
    run.elapsed = {"model": 0.0, "tools": 0.0}

    try:
        parsed = _parse_request(text)
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.stopped = "parsing_failed"
        _step(run, "parse", "model", "error", f"не вдалося розібрати звернення: {exc}", input_value={"text": text})
        store.save(run)
        return run

    run.route = parsed.get("kind")
    run.data["parsed"] = parsed
    _step(run, "parse", "model", "ok", "звернення розібрано", input_value={"text": text}, output_value=parsed)

    if parsed.get("kind") == "other":
        run.status = "handed_off"
        run.reply = "Це звернення не входить у автоматичну схему обробки. Оператор розбереться з ним вручну."
        _step(run, "route", "code", "ok", "звернення передано оператору вручну", output_value={"route": "other"})
        store.save(run)
        return run

    order_id = str(parsed.get("order_id") or "").strip()
    if not order_id:
        run.status = "needs_info"
        run.reply = "Для продовження вкажіть номер замовлення, яке стосується звернення."
        _step(run, "lookup", "code", "waiting", "бракує номера замовлення", output_value={"missing": "order_id"})
        store.save(run)
        return run

    try:
        order = service.get_order(order_id)
    except service.ShopError as exc:
        run.status = "failed"
        run.stopped = str(exc)
        run.reply = "Під час перевірки замовлення виникла помилка. Спробуйте ще раз або зверніться до оператора."
        _step(run, "lookup", "tool", "error", f"не вдалось отримати замовлення: {exc}", input_value={"order_id": order_id})
        store.save(run)
        return run

    run.data["order"] = order
    if str(order.get("customer_id")) != str(customer_id):
        run.status = "handed_off"
        run.reply = "Це замовлення належить іншому клієнтові, тому його треба передати оператору."
        _step(run, "ownership", "code", "rejected", "замовлення не належить поточному клієнту", input_value={"order_id": order_id})
        store.save(run)
        return run

    if parsed.get("kind") == "status":
        run.status = "done"
        run.reply = _status_message(order)
        _step(run, "reply", "model", "ok", "запит про статус оброблено", output_value={"reply": run.reply})
        store.save(run)
        return run

    item_name = parsed.get("item") or _extract_item_name(text, order)
    item = _match_item(order, item_name)
    if parsed.get("kind") == "return" and not item:
        run.status = "needs_info"
        run.reply = "Вкажіть товар із замовлення, який стосується звернення."
        _step(run, "item", "code", "waiting", "не вдалося визначити товар у замовлення", input_value={"order_id": order_id})
        store.save(run)
        return run

    if parsed.get("kind") == "cancel":
        if order.get("status") != "preparing":
            run.status = "done"
            run.reply = f"Скасувати замовлення {order_id} неможливо, бо його статус — {service.ORDER_STATUSES.get(order.get('status'), order.get('status'))}."
            _step(run, "policy", "code", "rejected", "скасування заборонено за статусом замовлення", output_value={"status": order.get("status")})
            store.save(run)
            return run
        pending = {
            "summary": f"Скасувати замовлення {order_id}",
            "tool": "cancel_order",
            "arguments": {"order_id": order_id},
            "grounds": ["замовлення ще готується", "власне замовлення клієнта"],
        }
        run.pending = pending
        run.status = "awaiting_approval"
        _step(run, "approval", "human", "waiting", "передано на підтвердження оператора", output_value=pending)
        store.save(run)
        return run

    reason = parsed.get("reason") or _infer_reason(text)
    quantity = 1
    if item is not None:
        for line in order.get("items", []):
            if str(line.get("sku")) == str(item.get("sku")):
                quantity = int(line.get("quantity", 1))
                break
    pending = {
        "summary": f"Оформити повернення товару {item['name']} із замовлення {order_id}",
        "tool": "create_return",
        "arguments": {
            "order_id": order_id,
            "sku": item["sku"],
            "reason": reason or "not_suitable",
            "quantity": quantity,
            "comment": text.strip()[:200],
        },
        "grounds": ["замовлення належить клієнту", "товар є в замовленні", "поточний статус дозволяє повернення"],
    }
    run.pending = pending
    run.status = "awaiting_approval"
    _step(run, "approval", "human", "waiting", "передано на підтвердження оператора", output_value=pending)
    store.save(run)
    return run


def resume(run_id: str, approve: bool, comment: str = "") -> Run:
    """Продовжити звернення після рішення оператора."""
    run = store.load(run_id)
    if run is None:
        raise KeyError(f"звернення {run_id} не знайдено")

    if run.pending is None:
        return run

    if run.status != "awaiting_approval":
        return run

    run.decision = {"approve": bool(approve), "comment": str(comment or "")}
    _step(run, "decision", "human", "ok" if approve else "rejected", str(comment or "рішення оператора"), input_value=run.decision)

    if not approve:
        run.status = "rejected"
        run.reply = "Повернення не оформлюється: оператор відхилив дію."
        run.pending = None
        store.save(run)
        return run

    pending = run.pending or {}
    tool_name = pending.get("tool")
    arguments = pending.get("arguments", {})
    try:
        if tool_name == "cancel_order":
            order = service.get_order(str(arguments["order_id"]))
            if str(order.get("customer_id")) != str(run.customer_id):
                raise service.PolicyViolation("цікаво, але це чужий замовлення")
            result = service.cancel_order(str(arguments["order_id"]))
            run.reply = f"Замовлення {result['order_id']} скасовано."
        elif tool_name == "create_return":
            order = service.get_order(str(arguments["order_id"]))
            if str(order.get("customer_id")) != str(run.customer_id):
                raise service.PolicyViolation("повернення для чужого замовлення заборонено")
            result = service.create_return(
                str(arguments["order_id"]),
                str(arguments["sku"]),
                str(arguments.get("reason", "not_suitable")),
                int(arguments.get("quantity", 1)),
                str(arguments.get("comment", "")),
            )
            run.reply = f"Заявка {result['return_id']} на повернення оформлена успішно."
        else:
            raise ValueError(f"невідомий інструмент для підтвердження: {tool_name!r}")
    except service.ShopError as exc:
        run.status = "failed"
        run.stopped = str(exc)
        run.reply = f"Підтвердження не виконалося: {exc}"
        _step(run, tool_name or "execute", "tool", "error", "виконання після підтвердження завершилося помилкою", input_value=arguments)
        run.pending = None
        store.save(run)
        return run

    run.pending = None
    run.status = "done"
    _step(run, tool_name or "execute", "tool", "ok", "дія виконана рівно один раз", input_value=arguments, output_value={"result": run.reply})
    store.save(run)
    return run
