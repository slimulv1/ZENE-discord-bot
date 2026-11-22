"""Small, dependency-free resilience primitives used across the bot.

Everything here is async-safe and event-loop friendly: delays use
``asyncio.sleep``, never ``time.sleep``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


class CircuitOpen(RuntimeError):
    """Raised when a dependency is temporarily disabled by its breaker."""


@dataclass(slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.25

    async def run(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        last: BaseException | None = None
        name = getattr(func, "__qualname__", str(func))
        for attempt in range(1, max(1, self.attempts) + 1):
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - boundary of a retry loop
                last = exc
                if attempt >= max(1, self.attempts):
                    break
                delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                delay *= 1.0 + random.uniform(-self.jitter, self.jitter)
                log.warning(
                    "retry %s %d/%d sau %.2fs: %s", name, attempt, self.attempts, delay, exc
                )
                await asyncio.sleep(max(0.0, delay))
        assert last is not None
        raise last


class CircuitBreaker:
    """CLOSED -> OPEN -> HALF_OPEN -> CLOSED state machine."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        half_open_successes: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        # Keep tests able to use short windows; production passes 30s.
        self.recovery_seconds = max(0.01, recovery_seconds)
        self.half_open_successes = max(1, half_open_successes)
        self._state = self.CLOSED
        self._failures = 0
        self._half_successes = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._state == self.OPEN and time.monotonic() - self._opened_at >= self.recovery_seconds:
            return self.HALF_OPEN
        return self._state

    async def allow(self) -> bool:
        async with self._lock:
            # Refresh derived state while holding the lock.
            if (
                self._state == self.OPEN
                and time.monotonic() - self._opened_at >= self.recovery_seconds
            ):
                self._state = self.HALF_OPEN
                self._half_successes = 0
            return self._state != self.OPEN

    async def success(self) -> None:
        async with self._lock:
            if self._state == self.HALF_OPEN:
                self._half_successes += 1
                if self._half_successes >= self.half_open_successes:
                    self._state = self.CLOSED
                    self._failures = 0
                    self._half_successes = 0
                    log.info("circuit %s -> CLOSED", self.name)
            else:
                self._failures = 0

    async def failure(self) -> None:
        async with self._lock:
            self._half_successes = 0
            self._failures += 1
            if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                log.warning("circuit %s -> OPEN sau %d lỗi", self.name, self._failures)


async def call_with_breaker(
    breaker: CircuitBreaker,
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    fallback: Any = None,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    """Run an external call behind a breaker; return ``fallback`` when degraded."""
    if not await breaker.allow():
        return fallback() if callable(fallback) else fallback
    try:
        result = await (policy.run(func, *args, **kwargs) if policy else func(*args, **kwargs))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - breaker boundary
        await breaker.failure()
        return fallback() if callable(fallback) else fallback
    await breaker.success()
    return result


class TokenBucket:
    """Async token bucket for per-key soft rate limiting."""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = max(0.001, rate)
        self.capacity = max(1.0, capacity if capacity is not None else rate)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        """Return the number of seconds the caller should wait (0 = allowed)."""
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
            self._updated = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            wait = (tokens - self._tokens) / self.rate
            self._tokens = 0.0
            return max(0.0, wait)


async def with_timeout(awaitable: Awaitable[Any], seconds: float) -> Any:
    """Never let an external call hang the event loop forever."""
    return await asyncio.wait_for(awaitable, timeout=max(0.1, seconds))
