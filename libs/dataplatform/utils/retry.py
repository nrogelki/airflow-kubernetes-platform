"""Retry with exponential backoff for flaky calls (APIs, FTP listings...).

Prefer Airflow task ``retries`` for whole-task failures; use this for a single
call inside a task where repeating the whole task would be expensive.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


def retry(
    times: int = 3,
    backoff_seconds: float = 2.0,
    max_backoff_seconds: float = 60.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    jitter: bool = True,
    sleep: Callable[[float], None] = time.sleep,
):
    """Decorator: retry ``times`` extra attempts with exponential backoff.

    >>> @retry(times=4, exceptions=(TimeoutError,))
    ... def fetch(): ...
    """
    if times < 0:
        raise ValueError("times must be >= 0")

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= times:
                        raise
                    delay = min(backoff_seconds * (2**attempt), max_backoff_seconds)
                    if jitter:
                        delay *= random.uniform(0.5, 1.0)
                    attempt += 1
                    log.warning("%s failed (%s). Retry %d/%d in %.1fs", func.__name__, exc, attempt, times, delay)
                    sleep(delay)

        return wrapper

    return decorator
