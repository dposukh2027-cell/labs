from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.context_manager import trim_history_for_budget
from app.errors import ApiAuthError, ApiRateLimitError, ApiTimeoutError, ApiUnavailableError, InvalidSchemaError
from app.model_client import call_model
from app.schema import SUPPORT_RESPONSE_SCHEMA, validate_support_response


app = FastAPI(title='Support Assistant')


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: List[Dict[str, str]] = Field(default_factory=list)
    strategy: str = 'context'


class ResponsePayload(BaseModel):
    response_text: str
    category: str
    based_on_rules: bool
    needs_clarification: bool
    escalate_to_operator: bool
    order_number: Optional[str] = None


@app.get('/', response_class=HTMLResponse)
async def index() -> str:
    return '''
    <html>
      <head><title>Support Assistant</title></head>
      <body>
        <h1>Support Assistant</h1>
        <form id="chat-form">
          <textarea id="message" rows="4" cols="60" placeholder="Write your message..."></textarea><br>
          <button type="submit">Send</button>
        </form>
        <pre id="result"></pre>
        <script>
          const form = document.getElementById('chat-form');
          const messageInput = document.getElementById('message');
          const result = document.getElementById('result');
          form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const body = { message: messageInput.value, history: [], strategy: 'context' };
            const response = await fetch('/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body)
            });
            const json = await response.json();
            result.textContent = JSON.stringify(json, null, 2);
          });
        </script>
      </body>
    </html>
    '''


@app.post('/chat')
async def chat(req: ChatRequest):
    if not settings.api_key:
        raise HTTPException(status_code=500, detail='OPENAI_API_KEY is missing. Create a local .env file.')

    history = trim_history_for_budget(req.history, settings.token_budget)

    try:
        raw = call_model(
            user_message=req.message,
            history=history,
            strategy=req.strategy,
            rules_path=Path(__file__).resolve().parent.parent / 'context.md',
            response_schema=SUPPORT_RESPONSE_SCHEMA,
            allow_fallback=False,
        )
    except Exception as exc:
        if 'authentication' in str(exc).lower():
            raise HTTPException(status_code=401, detail=str(ApiAuthError())) from exc
        if 'timeout' in str(exc).lower():
            raise HTTPException(status_code=504, detail=str(ApiTimeoutError())) from exc
        if 'rate limit' in str(exc).lower() or '429' in str(exc):
            raise HTTPException(status_code=429, detail=str(ApiRateLimitError())) from exc
        if 'unavailable' in str(exc).lower() or '503' in str(exc):
            raise HTTPException(status_code=503, detail=str(ApiUnavailableError())) from exc
        raise HTTPException(status_code=502, detail=f'Model call failed: {type(exc).__name__}: {exc}')

    if not validate_support_response(raw):
        raise HTTPException(status_code=422, detail=str(InvalidSchemaError()))

    try:
        parsed = ResponsePayload(**raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f'Payload validation failed: {exc.errors()}')

    return {
        'assistant_reply': parsed.model_dump(),
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'model': settings.model},
        'conversation_card': {
            'category': parsed.category,
            'needs_clarification': parsed.needs_clarification,
            'order_number': parsed.order_number,
            'escalate_to_operator': parsed.escalate_to_operator,
        },
    }
