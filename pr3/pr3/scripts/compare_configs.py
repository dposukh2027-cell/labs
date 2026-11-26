from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import settings
from app.llm import LLMService
from app.service import load_context


REQUESTS = [
    "Чи можна повернути товар, якщо я відкрив упаковку, але не користувався ним?",
    "Мені потрібна доставка у Львів, скільки часу це займе?",
    "Коли працює служба підтримки в неділю?",
    "Я хочу оплатити карткою, чи можна це зробити при отриманні?",
    "Який термін гарантії на смартфон?",
    "Що робити, якщо товар прийшов пошкодженим?",
    "Можна отримати знижку 15% на замовлення?",
]

CONFIGS = [
    {"name": "balanced", "temperature": 0.2, "top_p": 0.9, "max_tokens": 200},
    {"name": "creative", "temperature": 0.9, "top_p": 0.95, "max_tokens": 250},
]


async def main() -> None:
    if not settings.api_key:
        print("LLM_API_KEY is not set. Add it to .env before running compare script.")
        return

    context_text = load_context()
    llm = LLMService()
    results = []

    for index, message in enumerate(REQUESTS, start=1):
        for cfg in CONFIGS:
            try:
                response = await llm.generate(
                    message,
                    context_text,
                    temperature=cfg["temperature"],
                    top_p=cfg["top_p"],
                    max_tokens=cfg["max_tokens"],
                )
                results.append({
                    "request_index": index,
                    "request": message,
                    "config": cfg["name"],
                    "answer": response["answer"],
                    "model": response["model"],
                    "elapsed_seconds": response["elapsed_seconds"],
                })
            except Exception as exc:  # pragma: no cover - example script only
                results.append({
                    "request_index": index,
                    "request": message,
                    "config": cfg["name"],
                    "error": str(exc),
                })

    output_path = Path(__file__).resolve().parent.parent / "comparison_report.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Comparison results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
