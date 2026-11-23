import unittest

from zene_core.bot import build_bot
from zene_core.config import Config
from zene_core.state import RuntimeState


class GatewayConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        # No token is used by the constructor; no network is touched.
        self.bot = build_bot(
            Config.from_env({"DISCORD_TOKEN": "x" * 40}),
            RuntimeState(),
        )

    def test_only_needed_intents_are_enabled(self) -> None:
        intents = self.bot.intents
        self.assertTrue(intents.guilds)
        self.assertTrue(intents.guild_messages)
        self.assertTrue(intents.dm_messages)
        self.assertTrue(intents.message_content)
        for name in (
            "typing",
            "guild_reactions",
            "presences",
            "members",
            "voice_states",
            "invites",
            "integrations",
            "webhooks",
        ):
            self.assertFalse(getattr(intents, name), f"intent {name} should be off")

    def test_member_cache_and_message_cache_are_small(self) -> None:
        self.assertEqual(self.bot._connection.member_cache_flags.value, 0)
        self.assertEqual(self.bot._connection.max_messages, 100)

    def test_latency_stats_empty_and_populated(self) -> None:
        empty = self.bot.latency_stats()
        self.assertEqual(empty, {"latest_ms": None, "p50_ms": None, "p95_ms": None})
        self.bot._latency_ms.extend([100.0, 200.0, 300.0, 400.0, 500.0])
        stats = self.bot.latency_stats()
        self.assertEqual(stats["latest_ms"], 500.0)
        self.assertEqual(stats["p50_ms"], 300.0)
        self.assertEqual(stats["p95_ms"], 500.0)
