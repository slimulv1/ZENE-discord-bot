"""Bridge legacy blocking HTTP calls onto the async resilience layer.

Every network call from a command goes through here so the circuit breaker,
retry policy and timeout are actually used in production (not dead code).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .resilience import CircuitBreaker, RetryPolicy, call_with_breaker, with_timeout

log = logging.getLogger(__name__)

_BREAKERS: dict[str, CircuitBreaker] = {}
_POLICY = RetryPolicy(attempts=2, base_delay=0.3, max_delay=1.5, jitter=0.2)


def _breaker(name: str) -> CircuitBreaker:
    breaker = _BREAKERS.get(name)
    if breaker is None:
        breaker = CircuitBreaker(
            name, failure_threshold=3, recovery_seconds=30.0, half_open_successes=1
        )
        _BREAKERS[name] = breaker
    return breaker


async def _blocking_get(url: str, timeout: float) -> Any:
    """Run the blocking ``requests.get`` off the event loop."""
    import requests

    response = await asyncio.to_thread(requests.get, url, timeout=timeout)
    response.raise_for_status()
    return response


async def fetch_json(
    url: str,
    *,
    name: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[Any]:
    """Return parsed JSON, or ``None`` when the dependency is degraded."""

    async def call() -> Any:
        response = await with_timeout(_blocking_get(url, timeout), timeout + 2.0)
        return response.json()

    result = await call_with_breaker(
        _breaker(name or url),
        call,
        fallback=None,
        policy=_POLICY,
    )
    if result is None:
        log.info("external API degraded: %s", name or url)
    return result


async def fetch_text(
    url: str,
    *,
    name: Optional[str] = None,
    timeout: float = 10.0,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    data: Optional[bytes] = None,
) -> Optional[str]:
    """Return response text for non-JSON endpoints (e.g. form POST APIs)."""

    async def call() -> str:
        import requests

        def work() -> str:
            response = requests.request(
                method, url, timeout=timeout, headers=headers, data=data
            )
            response.raise_for_status()
            return response.text

        return await with_timeout(asyncio.to_thread(work), timeout + 2.0)

    return await call_with_breaker(
        _breaker(name or url),
        call,
        fallback=None,
        policy=_POLICY,
    )


def breaker_snapshot() -> dict[str, str]:
    return {name: breaker.state for name, breaker in _BREAKERS.items()}
