from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ServiceError(Exception):
    code: str
    message: str
    payload: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f'{self.code}: {self.message}'


class ApiAuthError(ServiceError):
    def __init__(self, message: str = 'Authentication failed.'):
        super().__init__('AUTH_ERROR', message)


class ApiTimeoutError(ServiceError):
    def __init__(self, message: str = 'Request timed out.'):
        super().__init__('TIMEOUT', message)


class ApiRateLimitError(ServiceError):
    def __init__(self, message: str = 'Rate limit exceeded.'):
        super().__init__('RATE_LIMIT', message)


class ApiUnavailableError(ServiceError):
    def __init__(self, message: str = 'Service unavailable.'):
        super().__init__('SERVICE_UNAVAILABLE', message)


class InvalidSchemaError(ServiceError):
    def __init__(self, message: str = 'Model output did not pass schema validation.'):
        super().__init__('INVALID_SCHEMA', message)
