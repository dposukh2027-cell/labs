"""UTC daily spending limit persisted atomically across process restarts."""

import datetime as dt
import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DAILY_USD = float(os.getenv("BUDGET_DAILY_USD", "1.00"))
WARN_AT = float(os.getenv("BUDGET_WARN_AT", "0.8"))
BUDGET_FILE = os.getenv("BUDGET_FILE", "state/budget.json")
_lock = threading.RLock()
_reservations: dict[int, float] = {}


class BudgetExceeded(Exception):
    def __init__(self, spent: float, limit: float, resets_at: str) -> None:
        super().__init__(f"денний ліміт витрат {limit:.2f} $ вичерпано "
                         f"(витрачено {spent:.4f} $); відновиться {resets_at}")
        self.spent = spent
        self.limit = limit
        self.resets_at = resets_at


def settings() -> dict:
    return {"daily_usd": DAILY_USD, "warn_at": WARN_AT, "file": BUDGET_FILE, "timezone": "UTC"}


def _today() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load(now: dt.datetime) -> dict:
    path = Path(BUDGET_FILE) if BUDGET_FILE else None
    if path is not None and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("day"), str):
            raise ValueError(f"Invalid budget state: {path}")
        if payload["day"] == now.date().isoformat():
            return {"day": payload["day"], "spent": max(0.0, float(payload.get("spent", 0)))}
    return {"day": now.date().isoformat(), "spent": 0.0}


def _save(state: dict) -> None:
    if not BUDGET_FILE:
        return
    path = Path(BUDGET_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, path)


def _resets_at(now: dt.datetime) -> str:
    tomorrow = now.date() + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time.min, tzinfo=dt.timezone.utc).isoformat()


def check(expected_cost: float | None = None) -> None:
    now = _today()
    with _lock:
        state = _load(now)
        thread_id = threading.get_ident()
        reserved = sum(_reservations.values()) - _reservations.get(thread_id, 0.0)
        expected = max(0.0, expected_cost or 0.0)
        projected = state["spent"] + reserved + expected
        if state["spent"] >= DAILY_USD or projected > DAILY_USD:
            _save(state)
            raise BudgetExceeded(state["spent"], DAILY_USD, _resets_at(now))
        _reservations[thread_id] = expected


def record(cost: float | None) -> None:
    if cost is None:
        return
    now = _today()
    with _lock:
        _reservations.pop(threading.get_ident(), None)
        state = _load(now)
        state["spent"] = round(state["spent"] + max(0.0, float(cost)), 9)
        _save(state)


def release() -> None:
    """Release a preflight reservation when no provider request was made."""
    with _lock:
        _reservations.pop(threading.get_ident(), None)


def status() -> dict:
    now = _today()
    with _lock:
        state = _load(now)
        _save(state)
        spent = state["spent"]
        reserved = sum(_reservations.values())
    return {
        "day": state["day"],
        "spent": spent,
        "limit": DAILY_USD,
        "reserved": reserved,
        "remaining": max(0.0, DAILY_USD - spent - reserved),
        "warning": DAILY_USD > 0 and spent + reserved >= DAILY_USD * WARN_AT,
        "exceeded": spent >= DAILY_USD,
        "resets_at": _resets_at(now),
    }
