from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.config import settings


def load_rules(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8')


def build_system_prompt(strategy: str, rules_text: str) -> str:
    base = (
        'You are a support assistant for an online store. '
        'Answer only from the store rules. If the answer is not in the rules, say so and do not invent facts. '
        'Keep the response concise, factual, and in the user language. '
        'If the customer gives an order number, keep it and reuse it without asking again. '
        'Return a valid JSON object that matches the schema precisely. '
        'Fields: response_text, category, based_on_rules, needs_clarification, escalate_to_operator, order_number. '
        'Examples: if the answer exists in the rules, set based_on_rules=true; if not, set based_on_rules=false and avoid guessing; '
        'if required information is missing, set needs_clarification=true; if a manual transfer is needed, set escalate_to_operator=true. '
        'The order number format is ORD-2026-1234.'
    )

    if strategy in {'structured', 'context'}:
        base += '\n\nRules:\n' + rules_text[:5000]

    if strategy == 'context':
        base += '\n\nUse the current conversation context, remember earlier facts, and keep the answer aligned with previous turns.'

    return base


def build_messages(user_message: str, history: Optional[List[Dict[str, str]]] = None, strategy: str = 'context', rules_text: str = '') -> List[Dict[str, str]]:
    messages = [{
        'role': 'system',
        'content': build_system_prompt(strategy, rules_text),
    }]

    history = history or []
    for item in history:
        if item.get('role') in {'user', 'assistant'}:
            messages.append({'role': item['role'], 'content': item['content']})

    messages.append({'role': 'user', 'content': user_message})
    return messages


def call_model(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    strategy: str = 'context',
    rules_path: Optional[Path] = None,
    response_schema: Optional[Dict[str, Any]] = None,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    rules_text = load_rules(rules_path) if rules_path else ''
    messages = build_messages(user_message, history, strategy, rules_text)

    response = client.chat.completions.create(
        model=settings.model,
        messages=messages,
        response_format={
            'type': 'json_schema',
            'json_schema': {
                'name': 'support_response',
                'schema': response_schema or {},
            },
        },
        temperature=0.1,
    )

    payload = json.loads(response.choices[0].message.content)
    return payload
