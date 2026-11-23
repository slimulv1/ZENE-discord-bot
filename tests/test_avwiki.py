import unittest
from unittest.mock import AsyncMock, patch

from zene_core import avwiki
from zene_core.avwiki import page_thumbnail, parse_idol_tag

DESCRIPTION = """<div class="actress-col clearfix">
<div class="actress-image">
<img src="https://image-optimizer.osusume.dmm.co.jp/actress/hayasaka_hime.jpg" alt="早坂ひめ" />
</div>
<div class="actress-data"><dl>
<dt>AV女優名<span class="small">：</span></dt>
<dd>早坂ひめ（はやさかひめ）- hime hayasaka</dd>
<dt>別名義<span class="small">：</span></dt>
<dd> - - - </dd>
<dt>生年月日<span class="small">：</span></dt>
<dd>2002年06月03日</dd>
<dt>サイズ<span class="small">：</span></dt>
<dd>T154 / B88-W57-H87</dd>
<dt>SNS<span class="small">：</span></dt>
<dd>X： - - - 　Instagram： - - - </dd>
</dl></div></div>"""


PAGE_HTML = """<article><header>
<div class="article-thumbnail text-center"><a class="image-link-border" href="https://www.mgstage.com/product/product_detail/ABF-358/"><img loading="lazy" src="https://image.mgstage.com/images/prestige/abf/358/pb_p_abf-358.jpg" srcset="... 504w, ... 800w" alt="ABF-358" /></a></div>
</header><section>body</section></article>"""


class PageThumbnailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        avwiki._THUMB_CACHE.clear()

    async def test_extracts_cover_from_article_header(self) -> None:
        with patch("zene_core.avwiki.fetch_text", new=AsyncMock(return_value=PAGE_HTML)) as mocked:
            url = await page_thumbnail("https://av-wiki.net/abf-358/")
        self.assertEqual(
            url,
            "https://image.mgstage.com/images/prestige/abf/358/pb_p_abf-358.jpg",
        )
        mocked.assert_awaited_once()

    async def test_missing_thumbnail_degrades_safely(self) -> None:
        with patch("zene_core.avwiki.fetch_text", new=AsyncMock(return_value="<html></html>")):
            self.assertEqual(await page_thumbnail("https://av-wiki.net/unknown/"), "")


class ParseIdolTagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parsed = parse_idol_tag(
            {
                "name": "早坂ひめ",
                "description": DESCRIPTION,
                "link": "https://av-wiki.net/av-actress/hayasaka-hime/",
                "count": 30,
            }
        )

    def test_profile_fields(self) -> None:
        self.assertEqual(self.parsed["romaji"], "hime hayasaka")
        self.assertEqual(self.parsed["birthdate"], "03/06/2002")
        self.assertEqual(self.parsed["height"], "154 cm")
        self.assertEqual(self.parsed["measurements"], "88 / 57 / 87")
        self.assertEqual(self.parsed["alias"], "")
        self.assertEqual(self.parsed["sns"], "")

    def test_avatar_and_unknown_fields(self) -> None:
        self.assertTrue(self.parsed["image"].endswith("hayasaka_hime.jpg"))
        self.assertEqual(self.parsed["origin"], "")
        self.assertEqual(self.parsed["hobbies"], "")

    def test_missing_description_degrades_safely(self) -> None:
        parsed = parse_idol_tag({"name": "Someone", "description": ""})
        self.assertEqual(parsed["name"], "Someone")
        self.assertEqual(parsed["measurements"], "")
        self.assertEqual(parsed["image"], "")
