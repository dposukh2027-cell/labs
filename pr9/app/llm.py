import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("LLM_API_KEY")
MODEL = os.getenv("LLM_MODEL")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "800"))
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))


class LLMError(Exception):
    """Помилка роботи з моделлю, зрозуміла решті застосунку."""


def get_client():
    """Повернути готовий до роботи клієнт сервісу — один на застосунок."""
    if not API_KEY or not BASE_URL:
        raise LLMError("LLM API не настроєне: перевірте .env")
    return OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=TIMEOUT)


def build_messages(question: str) -> list[dict]:
    """Скласти початковий список повідомлень агента."""
    return [
        {
            "role": "system",
            "content": (
                "Ти помічник підтримки магазину. Відповідай українською мовою. "
                "Використовуй лише факти з даних магазину, що доступні через інструменти. "
                "Не вигадуй номери замовлень, товарів або дат. Якщо даних не вистачає, "
                "попроси уточнення."
            ),
        },
        {"role": "user", "content": question},
    ]


def _response_to_dict(response) -> dict:
    message = response.choices[0].message
    tool_calls = []
    if getattr(message, "tool_calls", None):
        for call in message.tool_calls:
            tool_calls.append({
                "id": getattr(call, "id", None),
                "type": getattr(call, "type", None),
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            })
    content = getattr(message, "content", None)
    usage = getattr(response, "usage", None)
    usage_payload = None
    if usage is not None:
        usage_payload = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        }
    return {
        "content": content,
        "tool_calls": tool_calls,
        "model": getattr(response, "model", MODEL),
        "usage": usage_payload,
    }


def chat(messages: list[dict], tools: list[dict], tool_choice: str = "auto") -> dict:
    """Один виклик моделі з історією повідомлень і описами інструментів."""
    started = time.time()
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools or None,
            tool_choice=tool_choice,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMError(str(exc)) from exc
    payload = _response_to_dict(response)
    payload["elapsed"] = round(time.time() - started, 3)
    return payload


def complete(messages: list[dict], schema: dict | None = None) -> dict:
    """Одне звертання до моделі без інструментів — для кроків workflow."""
    started = time.time()
    try:
        client = get_client()
        kwargs = {
            "model": MODEL,
            "messages": messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "timeout": TIMEOUT,
        }
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "request_parse",
                    "schema": schema,
                    "strict": True,
                },
            }
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(str(exc)) from exc

    message = response.choices[0].message
    text = message.content or ""
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"text": text}
    usage = getattr(response, "usage", None)
    payload = {
        "text": text,
        "parsed": parsed,
        "model": getattr(response, "model", MODEL),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        } if usage is not None else {},
        "elapsed": round(time.time() - started, 3),
    }
    return payload
