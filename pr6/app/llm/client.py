from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.config import settings


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.model_name

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is missing. Add key to .env")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str) -> dict[str, Any]:
        start = time.time()
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                try:
                    error_data = response.json()
                except ValueError:
                    error_message = response.text
                else:
                    api_error = error_data.get("error") if isinstance(error_data, dict) else None
                    if isinstance(api_error, dict):
                        error_message = str(api_error.get("message") or api_error)
                    else:
                        error_message = response.text

                if self.api_key:
                    error_message = error_message.replace(self.api_key, "[redacted]")
                error_message = error_message.strip()[:1200] or exc.response.reason_phrase
                raise RuntimeError(
                    f"LLM API returned HTTP {exc.response.status_code}: {error_message}"
                ) from exc
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["_timing_ms"] = round((time.time() - start) * 1000, 2)
        return parsed
