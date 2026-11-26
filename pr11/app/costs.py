"""Estimate provider call cost from usage or a marked token estimate."""

import math
import os

from dotenv import load_dotenv

load_dotenv()

PRICE_INPUT = float(os.getenv("LLM_PRICE_INPUT_PER_1M", "0.30"))
PRICE_OUTPUT = float(os.getenv("LLM_PRICE_OUTPUT_PER_1M", "2.50"))
_cached = os.getenv("LLM_PRICE_CACHED_INPUT_PER_1M", "")
PRICE_CACHED_INPUT = float(_cached) if _cached else PRICE_INPUT * 0.25
MOCK_BILLABLE = os.getenv("MOCK_BILLABLE", "1") == "1"


def settings() -> dict:
    return {
        "input_per_1m": PRICE_INPUT,
        "output_per_1m": PRICE_OUTPUT,
        "cached_input_per_1m": PRICE_CACHED_INPUT,
        "mock_billable": MOCK_BILLABLE,
        "currency": "USD",
    }


def estimate(usage: dict | None, *, provider: str | None = None, model: str | None = None,
             text: str | None = None) -> tuple[float | None, bool]:
    """Return USD cost and whether any token counts had to be estimated."""
    del model
    if provider == "mock" and not MOCK_BILLABLE:
        return 0.0, False

    estimated = not isinstance(usage, dict)
    if estimated:
        token_count = math.ceil(len(text or "") / 3)
        input_tokens = token_count // 2
        output_tokens = token_count - input_tokens
        cached_tokens = 0
    else:
        input_value = usage.get("prompt_tokens")
        output_value = usage.get("completion_tokens")
        if input_value is None and output_value is None:
            token_count = math.ceil(len(text or "") / 3)
            input_tokens = token_count // 2
            output_tokens = token_count - input_tokens
            estimated = True
        else:
            estimated_total = math.ceil(len(text or "") / 3)
            input_tokens = (max(0, int(input_value)) if input_value is not None
                            else max(0, estimated_total - int(output_value or 0)))
            output_tokens = (max(0, int(output_value)) if output_value is not None
                             else max(0, estimated_total - input_tokens))
            estimated = input_value is None or output_value is None
        details = usage.get("prompt_tokens_details") or {}
        cached_tokens = min(input_tokens, max(0, int(details.get("cached_tokens", 0) or 0)))

    cost = (
        (input_tokens - cached_tokens) * PRICE_INPUT
        + cached_tokens * PRICE_CACHED_INPUT
        + output_tokens * PRICE_OUTPUT
    ) / 1_000_000
    return round(cost, 9), estimated
