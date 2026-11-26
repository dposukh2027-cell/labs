"""Per-client sliding-window request limit."""

import hashlib
import os
import threading
import time
from collections import defaultdict, deque

from dotenv import load_dotenv

load_dotenv()

PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
_lock = threading.Lock()
_requests: dict[str, deque[float]] = defaultdict(deque)


class RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"ліміт вичерпано, повторіть через {retry_after:.0f} с")
        self.retry_after = retry_after


def settings() -> dict:
    return {"per_minute": PER_MINUTE, "window_seconds": 60}


def acquire(client: str) -> None:
    now = time.monotonic()
    key = hashlib.sha256((client or "anonymous").encode("utf-8")).hexdigest()
    with _lock:
        if PER_MINUTE <= 0:
            raise RateLimited(60.0)
        timestamps = _requests[key]
        while timestamps and now - timestamps[0] >= 60:
            timestamps.popleft()
        if len(timestamps) >= PER_MINUTE:
            raise RateLimited(max(0.0, 60 - (now - timestamps[0])))
        timestamps.append(now)
        if len(_requests) > 5000:
            expired = [client_key for client_key, seen in _requests.items() if not seen]
            for client_key in expired:
                _requests.pop(client_key, None)
