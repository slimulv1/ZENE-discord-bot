"""Shared async HTTP layer with a single aiohttp session.

Why: discord.py already ships aiohttp. Reusing one ClientSession avoids a new
TCP/TLS handshake per command and keeps DNS cached, which matters for the
24/7 uptime goal. All calls still go through the circuit breaker registry.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import aiohttp

from .resilience import CircuitBreaker, RetryPolicy, call_with_breaker

log = logging.getLogger(__name__)

_BREAKERS: dict[str, CircuitBreaker] = {}
_POLICY = RetryPolicy(attempts=2, base_delay=0.3, max_delay=1.5, jitter=0.2)
_SESSION: Optional[aiohttp.ClientSession] = None
_SESSION_LOCK = asyncio.Lock()


def _breaker(name: str) -> CircuitBreaker:
    breaker = _BREAKERS.get(name)
    if breaker is None:
        breaker = CircuitBreaker(
            name, failure_threshold=3, recovery_seconds=30.0, half_open_successes=1
        )
        _BREAKERS[name] = breaker
    return breaker


def get_breaker(name: str) -> CircuitBreaker:
    """Public accessor so other adapters can share the same breaker registry."""
    return _breaker(name)


async def get_session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        async with _SESSION_LOCK:
            if _SESSION is None or _SESSION.closed:
                connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
                timeout = aiohttp.ClientTimeout(total=15)
                _SESSION = aiohttp.ClientSession(
                    connector=connector, timeout=timeout
                )
                log.info("aiohttp session created")
    return _SESSION


async def close_session() -> None:
    global _SESSION
    if _SESSION is not None and not _SESSION.closed:
        await _SESSION.close()
    _SESSION = None


async def _request(
    method: str,
    url: str,
    *,
    timeout: float,
    headers: Optional[dict[str, str]] = None,
    data: Optional[bytes] = None,
) -> bytes:
    session = await get_session()
    request_timeout = aiohttp.ClientTimeout(total=max(1.0, timeout))
    async with session.request(
        method, url, timeout=request_timeout, headers=headers, data=data
    ) as response:
        response.raise_for_status()
        # Read inside the context — returning the response would release the
        # connection before the caller parses the body ("Connection closed").
        return await response.read()


async def fetch_json(
    url: str,
    *,
    name: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[Any]:
    """Return parsed JSON, or ``None`` when the dependency is degraded."""

    async def call() -> Any:
        raw = await _request("GET", url, timeout=timeout)
        return json.loads(raw)

    result = await call_with_breaker(
        _breaker(name or url), call, fallback=None, policy=_POLICY
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
    async def call() -> str:
        raw = await _request(
            method, url, timeout=timeout, headers=headers, data=data
        )
        return raw.decode("utf-8", "replace")

    return await call_with_breaker(
        _breaker(name or url), call, fallback=None, policy=_POLICY
    )


def breaker_snapshot() -> dict[str, str]:
    return {name: breaker.state for name, breaker in _BREAKERS.items()}
