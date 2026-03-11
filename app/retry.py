from __future__ import annotations

import random
import time
from typing import Callable, TypeVar
from urllib.error import HTTPError, URLError

T = TypeVar("T")


class RetryError(Exception):
    pass


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (URLError, TimeoutError)):
        return True

    if isinstance(exc, HTTPError):
        return exc.code == 429 or 500 <= exc.code <= 599

    return False


def run_with_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.2,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_attempts or not _is_retryable(exc):
                break

            # Exponential backoff with light jitter.
            delay = base_delay_seconds * (2 ** (attempt - 1))
            jitter = random.uniform(0.0, delay * 0.1)
            time.sleep(delay + jitter)

    raise RetryError(f"Operation failed after {max_attempts} attempts") from last_exc
