"""Adapter nền tảng: dò metadata rẻ trước khi tải.

Tiếng Việt: `_MetaParser` đọc og:/twitter: meta (trong ~2MB head),
`MetaAdapter` dò media trực tiếp, `YtDlpAdapter` (tắt mặc định, to_thread).
日本語: `_MetaParser`（~2MB headのメタ）+ `MetaAdapter` + `YtDlpAdapter`（既定OFF）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from html.parser import HTMLParser

from yarl import URL

from ..net import fetch_text
from .guards import is_asset_url, registrable
from .models import ProbeResult

log = logging.getLogger(__name__)


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        key = values.get("property") or values.get("name")
        content = values.get("content")
        if key and content:
            self.meta[key.lower()] = content


class MetaAdapter:
    """Generic og:/twitter: meta tags — works for most public posts."""

    name = "meta"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        host = URL(url).host or ""
        html = await fetch_text(url, name=f"embedfix:{registrable(host)}", timeout=timeout)
        if not html:
            return ProbeResult("none", "", "", page_url=url)

        parser = _MetaParser()
        try:
            # Some sites (e.g. YouTube) put og: tags ~800KB into the head.
            parser.feed(html[:2_000_000])
        except Exception as exc:  # noqa: BLE001 - malformed HTML boundary
            log.debug("meta parse failed: %s", exc)
        meta = parser.meta

        title = meta.get("og:title") or meta.get("twitter:title") or ""
        author = meta.get("og:site_name") or meta.get("author") or ""
        context = meta.get("og:description") or ""
        videos = [
            meta.get("og:video:secure_url"),
            meta.get("og:video"),
            meta.get("twitter:player"),
        ]
        images = [meta.get("og:image"), meta.get("twitter:image")]
        candidates = videos + images

        def valid(item: str | None) -> bool:
            return bool(item) and is_asset_url(str(item), allowed_domains, proxy_hosts)

        media = tuple(dict.fromkeys(str(item) for item in candidates if valid(item)))
        has_video = any(valid(item) for item in videos)
        if has_video:
            kind = "video"
        elif len(media) > 1:
            kind = "gallery"
        elif media:
            kind = "image"
        else:
            kind = "none"

        nsfw = True if "nsfw" in meta else None
        return ProbeResult(kind, title, author, media, context, nsfw, url)


class YtDlpAdapter:
    """Metadata-only fallback using yt-dlp (no download by default)."""

    name = "ytdlp"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        def work() -> dict:
            import yt_dlp

            with yt_dlp.YoutubeDL(
                {"quiet": True, "noplaylist": True, "skip_download": True}
            ) as ydl:
                return ydl.extract_info(url, download=False) or {}

        try:
            info = await asyncio.wait_for(asyncio.to_thread(work), timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - third-party SDK boundary
            log.debug("yt-dlp probe failed: %s", exc)
            return ProbeResult("none", "", "", page_url=url)

        thumbnails = info.get("thumbnails") or []
        thumb = info.get("thumbnail")
        if not thumb and thumbnails and isinstance(thumbnails[-1], dict):
            thumb = thumbnails[-1].get("url")
        media: tuple[str, ...] = ()
        if thumb and is_asset_url(str(thumb), allowed_domains, proxy_hosts):
            media = (str(thumb),)
        return ProbeResult(
            "image" if media else "none",
            str(info.get("title") or ""),
            str(info.get("uploader") or ""),
            media,
            str(info.get("description") or "")[:2000],
            None,
            url,
        )
