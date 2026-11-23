import unittest

from zene_core.embedfix.guards import canonicalize, is_asset_url, url_hash
from zene_core.embedfix.models import ProbeResult
from zene_core.embedfix.modifiers import parse_modifiers
from zene_core.embedfix.views import build_view


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
