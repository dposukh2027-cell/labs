import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.config import settings
from app.model_client import call_model
from app.schema import SUPPORT_RESPONSE_SCHEMA


load_dotenv(Path(__file__).resolve().parent / '.env')


if __name__ == '__main__':
    print('API key present:', bool(settings.api_key))
    print('Base URL:', settings.base_url)
    print('Model:', settings.model)

    if not settings.api_key:
        print('No API key found. Add OPENAI_API_KEY to the local .env file to run the schema check.')
        raise SystemExit(0)

    probe = {
        'message': 'Check if the provider accepts JSON schema output.',
        'history': [],
        'strategy': 'context',
    }

    try:
        result = call_model(
            user_message=probe['message'],
            history=probe['history'],
            strategy=probe['strategy'],
            rules_path=Path(__file__).resolve().parent / 'context.md',
            response_schema=SUPPORT_RESPONSE_SCHEMA,
            allow_fallback=False,
        )
        print('Provider accepted schema:', True)
        print(json.dumps(result, ensure_ascii=False, indent=2)[:1500])
    except Exception as exc:  # pragma: no cover
        print('Provider accepted schema:', False)
        print(type(exc).__name__, exc)
