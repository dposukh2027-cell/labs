from __future__ import annotations

import json
from pathlib import Path

from app.model_client import call_model
from app.schema import SUPPORT_RESPONSE_SCHEMA, validate_support_response


TEST_CASES = [
    {
        'name': 'simple shipping question',
        'messages': [
            {'role': 'user', 'content': 'I need to know where my order is.'},
            {'role': 'assistant', 'content': 'Please share the order number.'},
            {'role': 'user', 'content': 'It is ORD-2026-1234.'},
        ],
        'current': 'Where is my parcel now?',
    },
    {
        'name': 'refund without support',
        'messages': [
            {'role': 'user', 'content': 'I want a refund.'},
        ],
        'current': 'My product is bad and I expect my money back immediately.',
    },
    {
        'name': 'there is no rule',
        'messages': [
            {'role': 'user', 'content': 'Can you promise a free gift?'}
        ],
        'current': 'Can you guarantee me a free gift on my next order?',
    },
    {
        'name': 'missing order number',
        'messages': [
            {'role': 'user', 'content': 'The package is delayed.'},
        ],
        'current': 'The package is delayed again.',
    },
    {
        'name': 'order number reused',
        'messages': [
            {'role': 'user', 'content': 'My order number is ORD-2026-7788.'},
            {'role': 'assistant', 'content': 'I can help with that. What happened?'},
            {'role': 'user', 'content': 'The package has not arrived the day after the expected date.'},
        ],
        'current': 'Please tell me whether I can still get it today.',
    },
]


def run_three_strategies():
    rules_path = Path(__file__).resolve().parent.parent / 'context.md'
    results = {}

    for strategy in ['fuzzy', 'structured', 'context']:
        strategy_outcomes = []
        for item in TEST_CASES:
            try:
                payload = call_model(
                    user_message=item['current'],
                    history=item['messages'],
                    strategy=strategy,
                    rules_path=rules_path,
                    response_schema=SUPPORT_RESPONSE_SCHEMA,
                    allow_fallback=False,
                )
                valid = validate_support_response(payload)
                strategy_outcomes.append({
                    'name': item['name'],
                    'valid_schema': valid,
                    'payload': payload,
                })
            except Exception as exc:  # pragma: no cover
                strategy_outcomes.append({
                    'name': item['name'],
                    'valid_schema': False,
                    'error': str(exc),
                })
        results[strategy] = strategy_outcomes

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run_three_strategies()
