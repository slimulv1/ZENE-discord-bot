"""Pure-logic regression tests — chạy: python -m unittest discover -s tests -v"""

from __future__ import annotations

import asyncio
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from zene_core import resilience
from zene_core.assets import AssetRegistry
from zene_core.config import Config, ConfigurationError
from zene_core.content import build_registry
from zene_core.triggers import Response, Trigger, TriggerRegistry, normalize


class ConfigTests(unittest.TestCase):
    def test_from_env_and_redaction(self) -> None:
        env = {
            "DISCORD_TOKEN": "fake-token-for-tests-1234567890",
            "ZENE_PREFIXES": "z/, !/",
            "ZENE_OWNER_IDS": "111, not-a-number, 222",
            "ZENE_LOG_LEVEL": "verbose",
            "HEALTH_PORT": "9090",
        }
        config = Config.from_env(env)
        self.assertEqual(config.command_prefixes, ("z/", "!/"))
        self.assertEqual(config.owner_ids, frozenset({111, 222}))
        self.assertEqual(config.log_level, "INFO")  # invalid -> safe default
        self.assertEqual(config.health_port, 9090)
        self.assertNotIn("fake-token", repr(config))
        self.assertNotIn("fake-token", config.summary())

    def test_missing_token_raises(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("zene_core.config.DEFAULT_TOKEN_FILE", Path(tmp) / "TOKEN.json"),
            self.assertRaises(ConfigurationError),
        ):
            Config.from_env({})


class TriggerTests(unittest.TestCase):
    def test_exact_contains_and_unicode(self) -> None:
        registry = TriggerRegistry()
        registry.add(Trigger("a", "exact", "xin chào", Response("text", "1")))
        registry.add(Trigger("b", "contains", "siuu", Response("text", "2"), priority=10))
        registry.finalize()

        self.assertEqual(registry.match("XIN CHÀO").trigger.name, "a")
        decomposed = unicodedata.normalize("NFD", "XIN CHÀO")
        self.assertEqual(registry.match(decomposed).trigger.name, "a")
        self.assertEqual(registry.match("anh ấy nói siuu nè").trigger.name, "b")
        self.assertIsNone(registry.match(""))
        self.assertEqual(normalize("  XIN CHÀO  "), "xin chào")

    def test_content_registry_builds(self) -> None:
        registry = build_registry()
        self.assertGreater(len(registry), 15)
        self.assertEqual(registry.match("tôi bị xúc phạm").trigger.kind, "exact")
        self.assertEqual(registry.match("300 bài code thiếu nhi").trigger.payload.kind, "choice")


class BreakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_half_open_closed(self) -> None:
        breaker = resilience.CircuitBreaker(
            "test", failure_threshold=1, recovery_seconds=0.05, half_open_successes=1
        )
        self.assertTrue(await breaker.allow())
        await breaker.failure()
        self.assertFalse(await breaker.allow())
        await asyncio.sleep(0.06)
        self.assertTrue(await breaker.allow())
        self.assertEqual(breaker.state, resilience.CircuitBreaker.HALF_OPEN)
        await breaker.success()
        self.assertEqual(breaker.state, resilience.CircuitBreaker.CLOSED)

    async def test_fallback_when_open(self) -> None:
        breaker = resilience.CircuitBreaker("fallback", failure_threshold=1, recovery_seconds=60)
        await breaker.failure()

        async def boom() -> str:
            raise RuntimeError("down")

        result = await resilience.call_with_breaker(breaker, boom, fallback=lambda: "degraded")
        self.assertEqual(result, "degraded")

    async def test_token_bucket(self) -> None:
        bucket = resilience.TokenBucket(rate=1.0, capacity=2.0)
        self.assertEqual(await bucket.acquire(), 0.0)
        self.assertEqual(await bucket.acquire(), 0.0)
        self.assertGreater(await bucket.acquire(), 0.0)


class AssetTests(unittest.TestCase):
    def test_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = AssetRegistry(root, root / "zene" / "data")
            self.assertIsNone(registry.path_for("../../etc/passwd"))
            self.assertIsNone(registry.path_for("missing.png"))

    def test_load_without_excel_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = AssetRegistry(root, root / "zene" / "data")
            registry.load()
            self.assertTrue(registry.loaded)
            self.assertEqual(registry.command_count, 0)


if __name__ == "__main__":
    unittest.main()
