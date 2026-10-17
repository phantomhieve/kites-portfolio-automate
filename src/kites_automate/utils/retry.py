"""
Resilience utilities: exponential backoff retry decorator.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_with_backoff(
    retries: int = 4,
    initial_delay: float = 1.5,
    backoff_factor: float = 2.0,
    max_delay: float = 45.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    retry_message: str = "Retrying after transient error",
) -> Callable[[F], F]:
    """Decorator to retry a function with exponential backoff and jitter."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exc: Exception | None = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    # If it's a rate limit or transient network error, back off
                    if attempt == retries:
                        func_name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func_name,
                            retries,
                            exc,
                        )
                        raise
                    jitter = random.uniform(0.1, 0.5) * delay
                    sleep_time = min(delay + jitter, max_delay)
                    logger.warning(
                        "%s (%s: %s). Attempt %d/%d; waiting %.1fs...",
                        retry_message,
                        exc.__class__.__name__,
                        exc,
                        attempt,
                        retries,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    delay *= backoff_factor
            if last_exc:
                raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
