"""av-wiki.net WordPress REST client for /code and /idol."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from urllib.parse import urlencode

from cachetools import TTLCache

from .net import fetch_json, get_breaker
from .resilience import call_with_breaker

log = logging.getLogger(__name__)

BASE = "https://av-wiki.net/wp-json/wp/v2"

# Bounded TTL caches: repeated /code and /idol calls never re-hit the API.
_LOOKUP_CACHE: TTLCache = TTLCache(maxsize=256, ttl=300)
_TRANSLATE_CACHE: TTLCache = TTLCache(maxsize=512, ttl=86400)


def _strip(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))).strip()


def _field(text: str, label: str) -> str:
    found = re.search(re.escape(label) + r"\s+([^\s]+)", text)
    return found.group(1) if found else ""


def parse_post(post: dict) -> dict:
    content_raw = post.get("content", {}).get("rendered", "")
    content = _strip(content_raw)
    image = re.search(r'<img[^>]+src=["\']([^"\']+)', content_raw)
    return {
        "title": _strip(post.get("title", {}).get("rendered", "")),
        "link": str(post.get("link", "")),
        "code": _field(content, "メーカー品番") or _field(content, "FANZA品番"),
        "fanza": _field(content, "FANZA品番"),
        "maker": _field(content, "メーカー"),
        "label": _field(content, "レーベル"),
        "series": _field(content, "シリーズ"),
        "actress": _field(content, "AV女優名"),
        "date": _field(content, "配信開始日"),
        "image": image.group(1) if image else "",
    }


async def dmm_image(code: str, api_id: str, affiliate_id: str) -> str:
    """Fallback cover URL from FANZA/DMM. Credentials come from env-backed Config."""
    if not code or not api_id or not affiliate_id:
        return ""

    def work() -> str:
        import dmm

        api = dmm.API(api_id=api_id, affiliate_id=affiliate_id)
        for kwargs in (
            {"site": "FANZA", "service": "digital", "keyword": code, "output": "json"},
            {"site": "FANZA", "keyword": code, "output": "json"},
        ):
            try:
                result = api.item_search(**kwargs)
                items = result.get("result", {}).get("items", [])
                if not items:
                    continue
                urls = items[0].get("imageURL", {})
                return urls.get("large") or urls.get("medium") or ""
            except Exception as exc:  # noqa: BLE001 - third-party SDK boundary
                log.debug("DMM image lookup failed: %s", exc)
                continue
        return ""

    async def call() -> str:
        return await asyncio.to_thread(work)

    return await call_with_breaker(get_breaker("dmm-image"), call, fallback="")


async def to_vietnamese(text: str) -> str:
    """Translate any detected language -> Vietnamese; keep original if API is down."""
    if not text:
        return ""
    cached = _TRANSLATE_CACHE.get(text)
    if cached is not None:
        return cached

    # deep_translator hits translate.google.com which rate-limits aggressively.
    # The gtx endpoint is the same service but tolerates our request rate.
    url = "https://translate.googleapis.com/translate_a/single?" + urlencode(
        {"client": "gtx", "sl": "auto", "tl": "vi", "dt": "t", "q": text}
    )
    data = await fetch_json(url, name="ja-vi")
    result = text
    if isinstance(data, list) and data and isinstance(data[0], list):
        translated = "".join(str(segment[0]) for segment in data[0] if segment and segment[0])
        if translated:
            result = translated
    if result != text:
        _TRANSLATE_CACHE[text] = result
    return result


def clean_title(text: str) -> str:
    """Drop the site's boilerplate tail from post titles."""
    return re.sub(r"\s*に出てるAV女優名まとめ\s*$", "", text or "").strip()


def bilingual(japanese: str, vietnamese: str) -> str:
    if not japanese:
        return vietnamese
    if not vietnamese or vietnamese == japanese:
        return japanese
    return f"🇻🇳 {vietnamese}\n🇯🇵 {japanese}"


def normalize_code(value: str) -> list[str]:
    value = value.strip()
    candidates = [value]
    if "-" in value:
        candidates.append(value.replace("-", ""))
    else:
        found = re.match(r"([a-zA-Z]+)(\d+)", value)
        if found:
            candidates.append(f"{found.group(1)}-{found.group(2)}")
    return list(dict.fromkeys(c for c in candidates if c))


async def search_code(code: str, limit: int = 3) -> list[dict]:
    candidates = normalize_code(code)
    key = ("code", candidates[0] if candidates else "", limit)
    cached = _LOOKUP_CACHE.get(key)
    if cached is not None:
        return cached
    for candidate in candidates:
        url = f"{BASE}/posts?{urlencode({'search': candidate, 'per_page': limit})}"
        data = await fetch_json(url, name="avwiki")
        if isinstance(data, list) and data:
            result = [parse_post(item) for item in data]
            _LOOKUP_CACHE[key] = result
            return result
    return []


async def search_idol(name: str, limit: int = 5) -> dict | None:
    key = ("idol", name.strip(), limit)
    cached = _LOOKUP_CACHE.get(key)
    if cached is not None:
        return cached
    tags_url = f"{BASE}/tags?{urlencode({'search': name.strip(), 'per_page': 10})}"
    tags = await fetch_json(tags_url, name="avwiki")
    if not isinstance(tags, list) or not tags:
        return None
    tag = tags[0]
    posts_url = f"{BASE}/posts?{urlencode({'tags': tag['id'], 'per_page': limit})}"
    posts = await fetch_json(posts_url, name="avwiki")
    works = [parse_post(item) for item in posts] if isinstance(posts, list) else []
    result = {
        "name": html.unescape(str(tag.get("name", ""))),
        "link": str(tag.get("link", "")),
        "count": tag.get("count", 0),
        "works": works,
    }
    _LOOKUP_CACHE[key] = result
    return result
