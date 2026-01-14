"""Retry logic with exponential backoff."""

import asyncio
from dataclasses import dataclass
from typing import Callable, TypeVar, Optional
from functools import wraps
import structlog

log = structlog.get_logger()

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (Exception,)


def with_retry(config: Optional[RetryConfig] = None):
    """Decorator for retry logic with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)

    Example:
        @with_retry(RetryConfig(max_attempts=5))
        async def fetch_data():
            return await api.get()
    """
    config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = min(
                            config.base_delay * (config.exponential_base ** attempt),
                            config.max_delay
                        )
                        log.warning(
                            "retry_attempt",
                            attempt=attempt + 1,
                            max_attempts=config.max_attempts,
                            delay=delay,
                            error=str(e),
                            function=func.__name__
                        )
                        await asyncio.sleep(delay)
                    else:
                        log.error(
                            "retry_exhausted",
                            attempts=config.max_attempts,
                            error=str(e),
                            function=func.__name__
                        )

            raise last_exception

        return wrapper
    return decorator


class RetryableOllamaClient:
    """Ollama client wrapper with automatic retries.

    Wraps an OllamaClient and adds retry logic for transient failures
    like connection errors and timeouts.
    """

    def __init__(self, client: 'OllamaClient', config: Optional[RetryConfig] = None):
        self.client = client
        self.config = config or RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            retryable_exceptions=(ConnectionError, TimeoutError, OSError)
        )

    async def chat(self, **kwargs):
        """Chat with retry logic."""
        @with_retry(self.config)
        async def _chat():
            return await self.client.chat(**kwargs)

        return await _chat()

    async def stream(self, **kwargs):
        """Stream with retry logic."""
        @with_retry(self.config)
        async def _stream():
            return await self.client.stream(**kwargs)

        return await _stream()

    def list_models(self):
        """List models (sync, no retry needed)."""
        return self.client.list_models()
