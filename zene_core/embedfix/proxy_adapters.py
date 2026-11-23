"""No-yt-dlp adapters using direct URLs and public embed proxies."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from collections.abc import Iterable

from cachetools import TTLCache
from yarl import URL

from ..net import fetch_json, fetch_text, get_session
from .adapters import _MetaParser
from .guards import is_asset_url
from .models import ProbeResult

log = logging.getLogger(__name__)

# Short-lived negative cache: a dead shortcode should not cost 5s on every resend.
_IFX_MISS_CACHE: TTLCache = TTLCache(maxsize=256, ttl=300)

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


def extract_item_url(
    item: dict,
    allowed_domains: Iterable[str],
    proxy_hosts: Iterable[str],
) -> str | None:
    """Pick the first valid asset URL from a FxEmbed media item."""
    candidates = [item.get("url"), item.get("thumbnail_url")]
    for variant in item.get("variants") or []:
        if isinstance(variant, dict):
            candidates.append(variant.get("url"))
    for candidate in candidates:
        if candidate and is_asset_url(str(candidate), allowed_domains, proxy_hosts):
            return str(candidate)
    return None


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

        tweet_media = tweet.get("media") or {}
        media_list = tweet_media.get("all") or tweet_media.get("videos") or []
        media_urls: list[str] = []
        has_video = False
        if isinstance(media_list, list):
            for item in media_list[:10]:
                if not isinstance(item, dict):
                    continue
                url = extract_item_url(item, allowed_domains, proxy_hosts)
                if not url:
                    continue
                media_urls.append(url)
                if item.get("type") == "video" or ".mp4" in url:
                    has_video = True
        media = tuple(dict.fromkeys(media_urls))
        if has_video:
            kind = "video"
        elif len(media) > 1:
            kind = "gallery"
        elif media:
            kind = "image"
        else:
            kind = "none"

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
        if not shortcode or shortcode in _IFX_MISS_CACHE:
            return ProbeResult("none", "", "", page_url=url)
        session = await get_session()
        # We only need response headers; waiting 25s per index made a single
        # broken reel block the worker for ~86s (10 sequential HEADs).
        head_timeout = min(timeout, 5.0)
        proxy_down = False

        async def head(index: int) -> tuple[str, bool] | None:
            nonlocal proxy_down
            media_url = f"https://ifx.up.railway.app/p/{shortcode}/media/{index}"
            try:
                async with session.head(
                    media_url, allow_redirects=True, timeout=head_timeout
                ) as response:
                    if response.status >= 500:
                        proxy_down = True
                        return None
                    content_type = response.headers.get("Content-Type") or ""
                    if response.status != 200 or not content_type.startswith(("video/", "image/")):
                        return None
                    try:
                        size = int(response.headers.get("Content-Length") or 0)
                    except ValueError:
                        size = 0
                    if size and size > max_bytes:
                        return None
                    if not is_asset_url(media_url, allowed_domains, proxy_hosts):
                        return None
                    return (media_url, content_type.startswith("video/"))
            except Exception as exc:  # noqa: BLE001 - proxy boundary
                log.debug("ifx probe failed: %s", exc)
                return None

        # media/0 exists whenever ifx has anything. Fail fast instead of
        # probing 9 more indices through a 500-ing proxy.
        first = await head(0)
        if first is None or proxy_down:
            _IFX_MISS_CACHE[shortcode] = True
            return ProbeResult("none", "", "", page_url=url)

        collected: list[tuple[str, bool]] = [first]
        # Remaining indices in small parallel batches; stop at first empty one.
        for start in range(1, 10, 3):
            batch = await asyncio.gather(
                *(head(index) for index in range(start, min(start + 3, 10))),
                return_exceptions=True,
            )
            items = [item for item in batch if isinstance(item, tuple)]
            if proxy_down or not items:
                break
            collected.extend(items)
        if not collected:
            return ProbeResult("none", "", "", page_url=url)
        has_video = any(is_video for _, is_video in collected)
        kind = (
            "video"
            if len(collected) == 1 and has_video
            else ("gallery" if len(collected) > 1 else "image")
        )
        # ifx does not expose a sensitivity flag. Without this, strict-NSFW
        # mode silently drops every Instagram post in a normal channel.
        return ProbeResult(kind, "", "", tuple(item for item, _ in collected), "", False, url)


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
        # tnktok proxy has no sensitivity metadata; avoid silent drops.
        return ProbeResult("video", "", "", (final,), "", False, url)


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
            # facebed metadata has no sensitivity field; avoid silent drops.
            return ProbeResult("video", "", "", (video,), "", False, url)
        return ProbeResult("link", "", "", page_url=rewritten)
