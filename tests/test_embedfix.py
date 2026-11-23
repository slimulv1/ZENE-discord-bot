import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, patch

from zene_core import content
from zene_core.assets import AssetRegistry
from zene_core.avwiki import _guess_source, looks_vietnamese
from zene_core.cogs.conversation import ConversationCog
from zene_core.cogs.embedfix import EmbedFixCog, _bot_badge_url, _compose_avatar_bytes
from zene_core.config import Config
from zene_core.content import fresh_commands, prepare_reload, reload_data
from zene_core.embedfix.guards import canonicalize, is_asset_url, rewrite_tiktok_link, url_hash
from zene_core.embedfix.models import ProbeResult
from zene_core.embedfix.modifiers import parse_modifiers
from zene_core.embedfix.proxy_adapters import (
    IfxAdapter,
    TiktokProxyAdapter,
    TikwmAdapter,
    extract_item_url,
    facebed_url,
    ig_shortcode,
    pick_best_mp4,
    tiktok_video_id,
    x_status_parts,
)
from zene_core.embedfix.router import route_for
from zene_core.embedfix.views import CarouselView, build_view


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


class AvatarBadgeTests(unittest.TestCase):
    def test_badge_source_prefers_application_icon(self) -> None:
        bot = SimpleNamespace(
            application=SimpleNamespace(icon=SimpleNamespace(url="https://cdn/icon.png")),
            user=SimpleNamespace(display_avatar=SimpleNamespace(url="https://cdn/user.png")),
        )
        self.assertEqual(_bot_badge_url(bot), "https://cdn/icon.png")
        bot_no_icon = SimpleNamespace(application=None, user=bot.user)
        self.assertEqual(_bot_badge_url(bot_no_icon), "https://cdn/user.png")

    def test_badge_is_composited_at_bottom_right(self) -> None:
        from io import BytesIO

        from PIL import Image

        def solid(color: str) -> bytes:
            out = BytesIO()
            Image.new("RGB", (64, 64), color).save(out, format="PNG")
            return out.getvalue()

        result = _compose_avatar_bytes(solid("red"), solid("blue"))
        self.assertTrue(result.startswith(b"\x89PNG"))
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.size, (256, 256))
            badge_pixel = image.getpixel((178, 178))
            self.assertGreater(badge_pixel[2], badge_pixel[0])  # blue, not red
            # Badge must stay inside the big circle: outer corner is transparent.
            self.assertEqual(image.getpixel((248, 248))[3], 0)


class NativeEmbedHintTests(unittest.TestCase):
    def test_collects_every_image_from_native_embeds(self) -> None:
        cfg = SimpleNamespace(
            media_allowed_domains={"instagram.com"},
            media_proxy_hosts={"ifx.up.railway.app"},
        )
        fake_self = SimpleNamespace(cfg=cfg)
        raw = "https://www.instagram.com/p/DgFP9UNIBIE/"
        embeds = [
            SimpleNamespace(
                url=raw,
                title="Post",
                description="caption",
                image=SimpleNamespace(url="https://scontent.cdninstagram.com/a.jpg"),
            ),
            SimpleNamespace(
                url=raw,
                title="",
                description="",
                image=SimpleNamespace(url="https://scontent.cdninstagram.com/b.jpg"),
            ),
        ]
        message = SimpleNamespace(embeds=embeds)
        hints, title, context = EmbedFixCog._embed_hints(fake_self, message, raw)
        self.assertEqual(
            hints,
            ("https://scontent.cdninstagram.com/a.jpg", "https://scontent.cdninstagram.com/b.jpg"),
        )
        self.assertEqual(title, "Post")
        self.assertEqual(context, "caption")


class IfxFailFastTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from zene_core.embedfix import proxy_adapters

        proxy_adapters._IFX_MISS_CACHE.clear()

    async def test_500_on_first_index_stops_immediately(self) -> None:
        class Response:
            status = 500
            headers: ClassVar[dict[str, str]] = {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def head(self, url: str, **kwargs):
                self.calls.append(url)
                return Response()

        session = Session()
        with patch(
            "zene_core.embedfix.proxy_adapters.get_session",
            new=AsyncMock(return_value=session),
        ):
            result = await IfxAdapter().probe(
                "https://instagram.com/reel/DgDG_dropmP/",
                {"instagram.com"},
                25.0,
                proxy_hosts={"ifx.up.railway.app"},
            )
        self.assertEqual(result.kind, "none")
        self.assertEqual(len(session.calls), 1)
        # Negative cache: a repeated link must not hit the dead proxy again.
        with patch(
            "zene_core.embedfix.proxy_adapters.get_session",
            new=AsyncMock(return_value=session),
        ):
            await IfxAdapter().probe(
                "https://instagram.com/reel/DgDG_dropmP/",
                {"instagram.com"},
                25.0,
                proxy_hosts={"ifx.up.railway.app"},
            )
        self.assertEqual(len(session.calls), 1)


class TiktokAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from zene_core.embedfix import proxy_adapters

        proxy_adapters._TIKTOK_MISS_CACHE.clear()

    def test_video_id_accepts_photo_and_reel(self) -> None:
        self.assertEqual(
            tiktok_video_id("https://www.tiktok.com/@a/photo/1234567890"), "1234567890"
        )
        self.assertEqual(tiktok_video_id("https://www.tiktok.com/@a/reel/1234567890"), "1234567890")

    async def test_zero_length_proxy_response_is_rejected(self) -> None:
        class Response:
            status = 200
            headers: ClassVar[dict[str, str]] = {"Content-Length": "0"}
            url = "https://v16.tiktokcdn-us.com/x?video_mp4=1"

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def head(self, url, **kwargs):
                return Response()

        with patch(
            "zene_core.embedfix.proxy_adapters.get_session",
            new=AsyncMock(return_value=Session()),
        ):
            result = await TiktokProxyAdapter().probe(
                "https://www.tiktok.com/@a/video/1234567890",
                {"tiktok.com"},
                10.0,
                proxy_hosts={"offload.tnktok.com"},
            )
        self.assertEqual(result.kind, "none")

    async def test_tikwm_returns_play_url(self) -> None:
        payload = {"data": {"play": "https://v16.tiktokcdn-us.com/x?video_mp4=1"}}

        class Response:
            status = 200

            async def json(self, **kwargs):
                return payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def get(self, url, **kwargs):
                return Response()

        with patch(
            "zene_core.embedfix.proxy_adapters.get_session",
            new=AsyncMock(return_value=Session()),
        ):
            result = await TikwmAdapter().probe(
                "https://www.tiktok.com/@a/video/1234567890",
                {"tiktok.com"},
                10.0,
                proxy_hosts={"offload.tnktok.com"},
            )
        self.assertEqual(result.kind, "video")
        self.assertEqual(len(result.media_urls), 1)

    def test_tiktok_link_rewrite(self) -> None:
        self.assertEqual(
            rewrite_tiktok_link("https://www.tiktok.com/@a/video/123?utm_source=x&u_code=y"),
            "https://www.tnktok.com/@a/video/123",
        )
        self.assertEqual(rewrite_tiktok_link("https://instagram.com/p/x"), "")


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


class NsfwGuardTests(unittest.TestCase):
    def test_strict_mode_allows_proxy_media_marked_non_sensitive(self) -> None:
        result = ProbeResult(
            "gallery", "", "", ("https://ifx.up.railway.app/p/x/media/0",), "", False, ""
        )
        fake_self = SimpleNamespace(cfg=SimpleNamespace(nsfw_enabled=True, media_strict_nsfw=True))
        ctx = SimpleNamespace(
            message=SimpleNamespace(channel=SimpleNamespace(is_nsfw=lambda: False))
        )
        self.assertTrue(EmbedFixCog._nsfw_allowed(fake_self, ctx, result))
        unknown = ProbeResult("gallery", "", "", ("https://x/",), "", None, "")
        self.assertFalse(EmbedFixCog._nsfw_allowed(fake_self, ctx, unknown))

        relaxed = SimpleNamespace(cfg=SimpleNamespace(nsfw_enabled=False, media_strict_nsfw=True))
        self.assertTrue(EmbedFixCog._nsfw_allowed(relaxed, ctx, unknown))


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonicalize_strips_tracking(self) -> None:
        url = await canonicalize(
            "https://www.x.com/status/1?utm_source=a&id=2&igshid=abc",
            {"x.com"},
        )
        self.assertTrue(url.startswith("https://x.com/status/1"))
        self.assertNotIn("utm_source", url)
        self.assertNotIn("igshid", url)

    async def test_canonicalize_strips_instagram_evlk(self) -> None:
        url = await canonicalize(
            "https://www.instagram.com/p/Df_8LXvH7xO/?utm_source=ig_web_copy_link&evlk=NTc4MTIwNjQ2YQ==&cnvx=NTc4MTIwNjQ2YQ==",
            {"instagram.com"},
        )
        self.assertEqual(url, "https://instagram.com/p/Df_8LXvH7xO/")
        self.assertNotIn("evlk", url)

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


class ViewTests(unittest.IsolatedAsyncioTestCase):
    def test_multi_image_gallery_uses_instagram_style_carousel(self) -> None:
        urls = (
            "https://pbs.twimg.com/1.jpg",
            "https://pbs.twimg.com/2.jpg",
            "https://pbs.twimg.com/3.jpg",
        )
        view = build_view(ProbeResult("gallery", "Tiêu đề", "", urls, "caption", False, ""))
        self.assertIsInstance(view, CarouselView)
        self.assertEqual(len(view.gallery.items), 1)
        self.assertEqual(len(view.row.children), 2)
        self.assertIn("1/3", view.text.content)

    async def test_carousel_callback_accepts_single_interaction_arg(self) -> None:
        # discord.py calls a manually assigned button callback as cb(interaction).
        view = CarouselView(("https://pbs.twimg.com/1.jpg", "https://pbs.twimg.com/2.jpg"))
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
        await view.forward.callback(interaction)
        self.assertEqual(view.index, 1)
        interaction.response.edit_message.assert_awaited_once()

    async def test_carousel_next_switches_image(self) -> None:
        urls = ("https://pbs.twimg.com/1.jpg", "https://pbs.twimg.com/2.jpg")
        view = CarouselView(urls, title="T", context="C")
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
        await view._on_forward(interaction, view.forward)
        self.assertEqual(view.index, 1)
        self.assertIn("2/2", view.text.content)
        interaction.response.edit_message.assert_awaited_once()

    def test_gallery_caps_at_nine_for_even_grid(self) -> None:
        urls = tuple(f"https://pbs.twimg.com/{i}.jpg" for i in range(12))
        result = ProbeResult("gallery", "Tiêu đề", "", urls, "", False, "")
        view = build_view(result)
        self.assertIsInstance(view, CarouselView)
        self.assertEqual(len(view.urls), 9)
        self.assertEqual(len(view.gallery.items), 1)

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
        self.assertIsInstance(view, CarouselView)
        self.assertEqual(len(components), 2)  # container + navigation row
        self.assertLessEqual(view.content_length(), 4000)
        self.assertLessEqual(len(components[0]["components"]), 10)


if __name__ == "__main__":
    unittest.main()
