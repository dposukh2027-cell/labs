from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional


SUPPORT_RESPONSE_SCHEMA: Dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'response_text': {'type': 'string', 'minLength': 1},
        'category': {
            'type': 'string',
            'enum': [
                'order_status',
                'shipping',
                'returns',
                'refund',
                'product_information',
                'payment',
                'account',
                'general',
            ],
        },
        'based_on_rules': {'type': 'boolean'},
        'needs_clarification': {'type': 'boolean'},
        'escalate_to_operator': {'type': 'boolean'},
        'order_number': {'type': ['string', 'null'], 'pattern': r'^ORD-\d{4}-\d{4}$|^$|^null$'},
    },
    'required': [
        'response_text',
        'category',
        'based_on_rules',
        'needs_clarification',
        'escalate_to_operator',
        'order_number',
    ],
}


def validate_support_response(payload: Dict[str, Any]) -> bool:
    import jsonschema

    try:
        jsonschema.validate(instance=payload, schema=SUPPORT_RESPONSE_SCHEMA)
        return True
    except jsonschema.ValidationError:
        return False
