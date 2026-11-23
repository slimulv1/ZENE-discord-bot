"""No-yt-dlp adapters using direct URLs and public embed proxies."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable

from yarl import URL

from ..net import fetch_json, fetch_text, get_session
from .adapters import _MetaParser
from .guards import is_asset_url
from .models import ProbeResult

log = logging.getLogger(__name__)

X_STATUS_RE = re.compile(r"^/([^/]+)/status/(\d+)")
IG_SHORTCODE_RE = re.compile(r"^/(?:p|reel|reels)/([^/?]+)")
TIKTOK_ID_RE = re.compile(r"/video/(\d+)")
MP4_RE = re.compile(r'https://video\.twimg\.com/[^"\\\s<>]+\.mp4\?[^"\\\s<>]*')
RES_RE = re.compile(r"/avc1/(\d+)x(\d+)/")


def x_status_parts(url: str) -> tuple[str, str] | None:
    match = X_STATUS_RE.match(URL(url).path)
    return (match.group(1), match.group(2)) if match else None


def ig_shortcode(url: str) -> str | None:
    match = IG_SHORTCODE_RE.match(URL(url).path)
    return match.group(1) if match else None


def tiktok_video_id(url: str) -> str | None:
    match = TIKTOK_ID_RE.search(URL(url).path)
    return match.group(1) if match else None


def facebed_url(url: str) -> str | None:
    parsed = URL(url)
    host = (parsed.host or "").lower().removeprefix("www.")
    if host not in {"facebook.com", "fb.com"}:
        return None
    return str(parsed.with_host("www.facebed.com"))


def pick_best_mp4(raw_html: str) -> str | None:
    candidates = [html.unescape(item) for item in MP4_RE.findall(raw_html)]
    if not candidates:
        return None

    def score(url: str) -> int:
        match = RES_RE.search(url)
        return int(match.group(1)) * int(match.group(2)) if match else 1

    return max(candidates, key=score)


class FxEmbedAdapter:
    name = "fxtwitter"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        parts = x_status_parts(url)
        if parts is None:
            return ProbeResult("none", "", "", page_url=url)
        user, status_id = parts
        payload = await fetch_json(
            f"https://api.fxtwitter.com/{user}/status/{status_id}", name="fxtwitter"
        )
        tweet = payload.get("tweet") if isinstance(payload, dict) else None
        if not isinstance(tweet, dict):
            return ProbeResult("none", "", "", page_url=url)

        media_list = (tweet.get("media") or {}).get("videos") or []
        first = media_list[0] if isinstance(media_list, list) and media_list else None
        media: tuple[str, ...] = ()
        kind = "none"
        if isinstance(first, dict):
            video_url = first.get("url")
            thumb = first.get("thumbnail_url")
            if video_url and is_asset_url(str(video_url), allowed_domains, proxy_hosts):
                media = (str(video_url),)
                kind = "video"
            elif thumb and is_asset_url(str(thumb), allowed_domains, proxy_hosts):
                media = (str(thumb),)
                kind = "image"

        author = (tweet.get("author") or {}).get("screen_name", "")
        return ProbeResult(
            kind,
            str(tweet.get("text") or "")[:2000],
            str(author),
            media,
            "",
            tweet.get("possibly_sensitive"),
            url,
        )


class XDirectAdapter:
    name = "x-direct"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        raw = await fetch_text(url, name="x-direct", timeout=timeout)
        candidate = pick_best_mp4(raw or "") if raw else None
        if not candidate or not is_asset_url(candidate, allowed_domains, proxy_hosts):
            return ProbeResult("none", "", "", page_url=url)
        return ProbeResult("video", "", "", (candidate,), "", None, url)


class IfxAdapter:
    name = "ifx"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        shortcode = ig_shortcode(url)
        if not shortcode:
            return ProbeResult("none", "", "", page_url=url)
        session = await get_session()
        for index in (0, 1, 2):
            media_url = f"https://ifx.up.railway.app/p/{shortcode}/media/{index}"
            try:
                async with session.head(
                    media_url, allow_redirects=True, timeout=timeout
                ) as response:
                    if response.status != 200:
                        continue
                    if "video" not in (response.headers.get("Content-Type") or ""):
                        continue
                    try:
                        size = int(response.headers.get("Content-Length") or 0)
                    except ValueError:
                        size = 0
                    if size and size > max_bytes:
                        continue
                    if not is_asset_url(media_url, allowed_domains, proxy_hosts):
                        continue
                    return ProbeResult("video", "", "", (media_url,), "", None, url)
            except Exception as exc:  # noqa: BLE001 - proxy boundary
                log.debug("ifx probe failed: %s", exc)
        return ProbeResult("none", "", "", page_url=url)


class TiktokProxyAdapter:
    name = "tnktok"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        video_id = tiktok_video_id(url)
        if video_id is None:
            return ProbeResult("none", "", "", page_url=url)
        proxy = f"https://offload.tnktok.com/generate/video/{video_id}"
        session = await get_session()
        try:
            async with session.head(proxy, allow_redirects=True, timeout=timeout) as response:
                if response.status != 200:
                    return ProbeResult("none", "", "", page_url=url)
                final = str(response.url)
        except Exception as exc:  # noqa: BLE001 - proxy boundary
            log.debug("tnktok probe failed: %s", exc)
            return ProbeResult("none", "", "", page_url=url)

        parsed = URL(final)
        host = (parsed.host or "").lower()
        is_cdn = host.endswith((".tiktokcdn.com", ".tiktokcdn-us.com"))
        if not is_cdn or "video_mp4" not in parsed.query_string:
            return ProbeResult("none", "", "", page_url=url)
        if not is_asset_url(final, allowed_domains, proxy_hosts):
            return ProbeResult("none", "", "", page_url=url)
        return ProbeResult("video", "", "", (final,), "", None, url)


class FacebedAdapter:
    name = "facebed"

    async def probe(
        self,
        url: str,
        allowed_domains: Iterable[str],
        timeout: float,
        proxy_hosts: Iterable[str] = (),
        max_bytes: int = 8 * 1024 * 1024,
    ) -> ProbeResult:
        rewritten = facebed_url(url)
        if rewritten is None:
            return ProbeResult("none", "", "", page_url=url)
        raw = await fetch_text(rewritten, name="facebed", timeout=timeout)
        if not raw:
            return ProbeResult("link", "", "", page_url=rewritten)
        parser = _MetaParser()
        parser.feed(raw[:1_000_000])
        video = parser.meta.get("og:video:secure_url") or parser.meta.get("og:video")
        if video and is_asset_url(video, allowed_domains, proxy_hosts):
            return ProbeResult("video", "", "", (video,), "", None, url)
        return ProbeResult("link", "", "", page_url=rewritten)
