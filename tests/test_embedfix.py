import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zene_core import content
from zene_core.assets import AssetRegistry
from zene_core.avwiki import _guess_source, looks_vietnamese
from zene_core.cogs.conversation import ConversationCog
from zene_core.config import Config
from zene_core.content import fresh_commands, prepare_reload, reload_data
from zene_core.embedfix.guards import canonicalize, is_asset_url, url_hash
from zene_core.embedfix.models import ProbeResult
from zene_core.embedfix.modifiers import parse_modifiers
from zene_core.embedfix.proxy_adapters import (
    extract_item_url,
    facebed_url,
    ig_shortcode,
    pick_best_mp4,
    tiktok_video_id,
    x_status_parts,
)
from zene_core.embedfix.router import route_for
from zene_core.embedfix.views import build_view


class ConfigTests(unittest.TestCase):
    def test_proxy_enabled_by_default(self) -> None:
        config = Config.from_env({"DISCORD_TOKEN": "x" * 40})
        self.assertTrue(config.media_use_proxies)
        disabled = Config.from_env({"DISCORD_TOKEN": "x" * 40, "ZENE_MEDIA_USE_PROXIES": "false"})
        self.assertFalse(disabled.media_use_proxies)
        self.assertTrue(config.media_auto_translate)
        no_translate = Config.from_env(
            {"DISCORD_TOKEN": "x" * 40, "ZENE_MEDIA_AUTO_TRANSLATE": "false"}
        )
        self.assertFalse(no_translate.media_auto_translate)
        impersonate = Config.from_env({"DISCORD_TOKEN": "x" * 40, "ZENE_MEDIA_MODE": "impersonate"})
        self.assertEqual(impersonate.media_mode, "impersonate")
        self.assertTrue(config.reload_on_change)
        self.assertFalse(
            Config.from_env(
                {"DISCORD_TOKEN": "x" * 40, "ZENE_RELOAD_ON_CHANGE": "false"}
            ).reload_on_change
        )


class FreshCommandsTests(unittest.TestCase):
    def test_reads_from_disk_each_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memes.json"
            path.write_text(
                json.dumps(
                    {
                        "assets": {"meme mới": "zene/data/image/a.png"},
                        "text_triggers": {"chào bot": "hello"},
                        "folder_triggers": {},
                        "choice_triggers": {},
                        "contains_triggers": [{"pattern": "siuuu"}],
                    }
                ),
                encoding="utf-8",
            )
            with patch("zene_core.content.DATA_FILE", path):
                self.assertEqual(fresh_commands("assets"), ["meme mới"])
                names = fresh_commands()
                self.assertIn("chào bot", names)
                self.assertIn("siuuu", names)


class ReloadDataTests(unittest.TestCase):
    def test_reload_mutates_in_place_and_rejects_bad_file(self) -> None:
        original = {
            "DATA": content.DATA,
            "MESSAGES": content.MESSAGES.copy(),
            "COMMAND_TEXTS": content.COMMAND_TEXTS.copy(),
            "ANXIN_STORIES": content.ANXIN_STORIES[:],
            "CODE_STORIES": content.CODE_STORIES[:],
            "FOLO_TEXT": content.FOLO_TEXT,
        }
        good = {
            "text_triggers": {"câu mới": "rồi"},
            "contains_triggers": [
                {"name": "folo", "pattern": "folo", "response": {"kind": "text", "value": " FolO "}}
            ],
            "folder_triggers": {"thư mục mới": "haohan"},
            "choice_triggers": {"300 bài code thiếu nhi": ["câu 1", "câu 2"]},
            "command_texts": {"hotro": "nhắn lại nha"},
            "anxin_stories": [" chuyện 1 "],
            "assets": {"ảnh mới": "zene/data/image/a.png"},
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "memes.json"
                path.write_text(json.dumps(good), encoding="utf-8")
                with patch("zene_core.content.DATA_FILE", path):
                    registry = reload_data()
                    self.assertIsNotNone(registry.match("câu mới"))
                    self.assertIsNotNone(registry.match("folo"))
                    # Imported references see the new data because of in-place mutation.
                    self.assertIn("câu mới", content.MESSAGES)
                    self.assertEqual(content.COMMAND_TEXTS["hotro"], "nhắn lại nha")
                    self.assertEqual(content.ANXIN_STORIES, [" chuyện 1 "])

                    # Missing section -> ValueError, last good data untouched.
                    broken = dict(good)
                    broken.pop("assets")
                    path.write_text(json.dumps(broken), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        reload_data()
                    self.assertIn("câu mới", content.MESSAGES)
                    self.assertEqual(content.COMMAND_TEXTS["hotro"], "nhắn lại nha")
        finally:
            content.DATA = original["DATA"]
            content.MESSAGES.clear()
            content.MESSAGES.update(original["MESSAGES"])
            content.COMMAND_TEXTS.clear()
            content.COMMAND_TEXTS.update(original["COMMAND_TEXTS"])
            content.ANXIN_STORIES[:] = original["ANXIN_STORIES"]
            content.CODE_STORIES[:] = original["CODE_STORIES"]
            content.FOLO_TEXT = original["FOLO_TEXT"]


class RouterTests(unittest.TestCase):
    def test_x_routes_to_fast_api_first(self) -> None:
        self.assertEqual(route_for("https://x.com/user/status/1", True)[0], "fxtwitter")

    def test_proxy_off_falls_back_to_meta(self) -> None:
        self.assertEqual(route_for("https://x.com/user/status/1", False), ("meta",))

    def test_unknown_domain_uses_meta(self) -> None:
        self.assertEqual(route_for("https://youtube.com/watch?v=1", True), ("meta",))

    def test_vietnamese_detection(self) -> None:
        self.assertTrue(looks_vietnamese("Tiếng Việt"))
        self.assertFalse(looks_vietnamese("Hello world"))
        # A single Portuguese 'é' must not be treated as Vietnamese.
        self.assertFalse(looks_vietnamese("Esse é de longe o melhor"))

    def test_source_guess(self) -> None:
        self.assertEqual(_guess_source("习近平向李在明赠送手机"), "zh-CN")
        self.assertEqual(_guess_source("Hello world"), "en")


class PrepareReloadTests(unittest.TestCase):
    def test_bad_type_does_not_touch_live_state(self) -> None:
        snapshot = dict(content.COMMAND_TEXTS)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memes.json"
            broken = {
                "text_triggers": {},
                "contains_triggers": [],
                "folder_triggers": {},
                "choice_triggers": {},
                "command_texts": {"hotro": "MỚI"},
                "anxin_stories": [],
                "assets": [],  # wrong type -> AttributeError if committed
            }
            path.write_text(json.dumps(broken), encoding="utf-8")
            with patch("zene_core.content.DATA_FILE", path), self.assertRaises(TypeError):
                prepare_reload()
        self.assertEqual(content.COMMAND_TEXTS, snapshot)
        self.assertNotEqual(content.COMMAND_TEXTS.get("hotro"), "MỚI")


class HotReloadPerfTests(unittest.TestCase):
    def test_poll_interval_default_and_clamp(self) -> None:
        self.assertEqual(Config.from_env({"DISCORD_TOKEN": "x" * 40}).reload_poll_seconds, 30.0)
        env = {"DISCORD_TOKEN": "x" * 40, "ZENE_RELOAD_POLL_SECONDS": "1"}
        self.assertEqual(Config.from_env(env).reload_poll_seconds, 5.0)
        env["ZENE_RELOAD_POLL_SECONDS"] = "9999"
        self.assertEqual(Config.from_env(env).reload_poll_seconds, 3600.0)

    def test_assets_load_reuses_parsed_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "memes.json").write_text("{ this is NOT json", encoding="utf-8")
            registry = AssetRegistry(root, root)
            # Valid dict passed in: must be used, broken file on disk ignored.
            registry.load({"assets": {"meme": "zene/data/image/a.png"}})
            self.assertEqual(registry.file_for_command("meme"), "zene/data/image/a.png")

    def test_cooldowns_keep_unchanged_buckets(self) -> None:
        trigger = SimpleNamespace(name="text:siuu", cooldown=0.0)
        bot = SimpleNamespace(
            config=SimpleNamespace(trigger_cooldown=1.5),
            triggers=SimpleNamespace(all=(trigger,)),
        )
        cog = ConversationCog(bot)
        original = cog._cooldowns["text:siuu"]
        cog.rebuild_cooldowns()
        self.assertIs(cog._cooldowns["text:siuu"], original)

        trigger.cooldown = 9.0
        cog.rebuild_cooldowns()
        self.assertIsNot(cog._cooldowns["text:siuu"], original)


class ModifierTests(unittest.TestCase):
    def test_prefix_modifiers(self) -> None:
        _, mods, lang = parse_modifiers("文 es: xem cái này || ")
        self.assertIn("translate", mods)
        self.assertIn("spoiler", mods)
        self.assertEqual(lang, "es")

    def test_modifiers_inside_url_are_ignored(self) -> None:
        text = "xem https://tiktok.com/@a/video/1?u=~x||y "
        _, mods, _ = parse_modifiers(text)
        self.assertFalse(mods)

    def test_parent_and_hide_quote(self) -> None:
        _, mods, _ = parse_modifiers("^ ~ link ")
        self.assertIn("parent", mods)
        self.assertIn("hide_quote", mods)


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonicalize_strips_tracking(self) -> None:
        url = await canonicalize(
            "https://www.x.com/status/1?utm_source=a&id=2&igshid=abc",
            {"x.com"},
        )
        self.assertTrue(url.startswith("https://x.com/status/1"))
        self.assertNotIn("utm_source", url)
        self.assertNotIn("igshid", url)

    async def test_domain_spoof_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await canonicalize("https://evil-x.com/post/1", {"x.com"})

    def test_asset_url_validation(self) -> None:
        self.assertTrue(is_asset_url("https://pbs.twimg.com/a.jpg", {"x.com"}))
        self.assertFalse(is_asset_url("http://pbs.twimg.com/a.jpg", {"x.com"}))
        self.assertFalse(is_asset_url("https://127.0.0.1/a.jpg", {"x.com"}))
        self.assertTrue(is_asset_url("attachment://clip.mp4", {"x.com"}))

    def test_hash_is_stable(self) -> None:
        self.assertEqual(url_hash("https://x.com/a"), url_hash("https://x.com/a"))


class ProxyTests(unittest.TestCase):
    def test_x_status_parts(self) -> None:
        self.assertEqual(x_status_parts("https://x.com/user/status/123?s=20"), ("user", "123"))

    def test_ig_shortcode_reels(self) -> None:
        self.assertEqual(
            ig_shortcode("https://www.instagram.com/reels/DgAY0euJkFt/"), "DgAY0euJkFt"
        )

    def test_facebed_rewrite(self) -> None:
        self.assertEqual(
            facebed_url("https://www.facebook.com/reel/1811869953192242"),
            "https://www.facebed.com/reel/1811869953192242",
        )
        self.assertIsNone(facebed_url("https://x.com/user/status/1"))

    def test_extract_item_url(self) -> None:
        item = {
            "type": "video",
            "url": "https://video.twimg.com/a/vid/avc1/480x854/x.mp4?tag=29",
            "variants": [],
        }
        self.assertEqual(extract_item_url(item, frozenset({"x.com"}), frozenset()), item["url"])
        self.assertIsNone(extract_item_url({"url": "http://bad/x"}, frozenset(), frozenset()))

    def test_tiktok_video_id(self) -> None:
        self.assertEqual(
            tiktok_video_id("https://www.tiktok.com/@user/video/7581405645870517512"),
            "7581405645870517512",
        )

    def test_pick_best_mp4(self) -> None:
        raw = (
            "https://video.twimg.com/a/vid/avc1/320x568/low.mp4?tag=29&amp;v=1"
            "https://video.twimg.com/a/vid/avc1/480x854/high.mp4?tag=29"
        )
        picked = pick_best_mp4(raw)
        self.assertIsNotNone(picked)
        self.assertIn("high.mp4", str(picked))
        self.assertIn("&v=1", str(picked))

    def test_proxy_host_allowed_for_asset(self) -> None:
        self.assertTrue(
            is_asset_url(
                "https://ifx.up.railway.app/p/abc/media/0",
                {"instagram.com"},
                {"ifx.up.railway.app"},
            )
        )
        self.assertFalse(
            is_asset_url("https://ifx.up.railway.app/p/abc/media/0", {"instagram.com"})
        )


class ViewTests(unittest.TestCase):
    def test_components_v2_layout(self) -> None:
        result = ProbeResult(
            "gallery",
            "Tiêu đề",
            "tác giả",
            ("https://pbs.twimg.com/1.jpg", "https://pbs.twimg.com/2.jpg"),
            "ngữ cảnh",
        )
        view = build_view(result, spoiler=True)
        components = view.to_components()
        self.assertEqual(len(components), 1)
        self.assertLessEqual(view.content_length(), 4000)
        self.assertLessEqual(len(components[0]["components"]), 10)


if __name__ == "__main__":
    unittest.main()
