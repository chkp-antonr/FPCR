"""Shared utilities for FPCR."""

import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast, overload

from arlogi import get_logger

logger = get_logger(__name__)


@overload
def log_elapsed_time[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]: ...


@overload
def log_elapsed_time[**P, R](func: Callable[P, R]) -> Callable[P, R]: ...


def log_elapsed_time(func: Callable[..., object]) -> Callable[..., object]:
    """Decorator to log elapsed time for both sync and async functions.

    Automatically detects whether the function is synchronous or asynchronous
    and logs the function name and elapsed time in seconds as a warning.

    Args:
        func: The function to decorate (sync or async)

    Returns:
        The wrapped function with timing logging

    Examples:
        >>> @log_elapsed_time
        ... def my_sync_function():
        ...     pass

        >>> @log_elapsed_time
        ... async def my_async_function():
        ...     pass
    """

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.time()
        awaited_func = cast(Callable[..., Awaitable[object]], func)
        try:
            result = await awaited_func(*args, **kwargs)
        except SystemExit:
            end = time.time()
            logger.warning(f"time elapsed in {func.__name__}: {end - start:.2f}s")  # type: ignore[attr-defined]
            raise
        end = time.time()
        logger.warning(f"time elapsed in {func.__name__}: {end - start:.2f}s")  # type: ignore[attr-defined]
        return result

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.time()
        try:
            result = func(*args, **kwargs)
        except SystemExit:
            end = time.time()
            logger.warning(f"time elapsed in {func.__name__}: {end - start:.2f}s")  # type: ignore[attr-defined]
            raise
        end = time.time()
        logger.warning(f"time elapsed in {func.__name__}: {end - start:.2f}s")  # type: ignore[attr-defined]
        return result

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
