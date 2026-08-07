import asyncio
import functools
import logging
import time
import traceback
from typing import Any, Callable, Optional, TypeVar

from fastapi import HTTPException
from langsmith import traceable
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ============================================================
# 1. Async Logging
# ============================================================
def async_log(func: F) -> F:
    """Structured logging for async functions."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        func_name = func.__qualname__
        logger.info(f"→ Starting {func_name}")
        try:
            result = await func(*args, **kwargs)
            duration = time.perf_counter() - start
            logger.info(f"← Finished {func_name} in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            logger.exception(f"✖ Error in {func_name} after {duration:.3f}s | {type(e).__name__}: {e}")
            raise
    return wrapper  # type: ignore


def sync_log(func: F) -> F:
    """Structured logging for sync functions."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        func_name = func.__qualname__
        logger.info(f"→ Starting {func_name}")
        try:
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start
            logger.info(f"← Finished {func_name} in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            logger.exception(f"✖ Error in {func_name} after {duration:.3f}s | {type(e).__name__}: {e}")
            raise
    return wrapper  # type: ignore


# ============================================================
# 2. Global / Function-level Error Handling
# ============================================================
def async_error_handler(
    default_return: Any = None,
    reraise: bool = True,
    http_status: int = 500,
):
    """
    Global-style async error handler decorator.
    - Logs full traceback
    - Optionally converts to HTTPException
    - Can return a default value or re-raise
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Let FastAPI HTTPExceptions pass through
                raise
            except Exception as e:
                logger.error(
                    f"Unhandled error in {func.__qualname__}: {type(e).__name__}: {e}\n"
                    f"{traceback.format_exc()}"
                )
                if reraise:
                    # Convert to HTTPException for API layer
                    raise HTTPException(
                        status_code=http_status,
                        detail=f"Internal error in {func.__name__}: {str(e)}",
                    )
                return default_return
        return wrapper  # type: ignore
    return decorator


# ============================================================
# 3. Retry
# ============================================================
def async_retry(
    attempts: int = 3,
    min_wait: float = 1,
    max_wait: float = 10,
    exceptions: tuple = (Exception,),
):
    def decorator(func: F) -> F:
        @functools.wraps(func)
        @retry(
            retry=retry_if_exception_type(exceptions),
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            reraise=True,
        )
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


# ============================================================
# 4. Simple Async Cache
# ============================================================
_cache: dict[str, Any] = {}
_cache_lock = asyncio.Lock()


def async_cache(ttl_seconds: int = 300):
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = f"{func.__qualname__}:{str(args)}:{str(sorted(kwargs.items()))}"
            async with _cache_lock:
                if key in _cache:
                    value, timestamp = _cache[key]
                    if time.time() - timestamp < ttl_seconds:
                        logger.debug(f"Cache HIT → {func.__qualname__}")
                        return value
            result = await func(*args, **kwargs)
            async with _cache_lock:
                _cache[key] = (result, time.time())
            return result
        return wrapper  # type: ignore
    return decorator


# ============================================================
# 5. LangSmith Function-level Tracing
# ============================================================
def langsmith_trace(name: Optional[str] = None, run_type: str = "chain"):
    def decorator(func: F) -> F:
        return traceable(name=name or func.__qualname__, run_type=run_type)(func)  # type: ignore
    return decorator