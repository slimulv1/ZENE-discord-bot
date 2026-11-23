"""av-wiki.net WordPress REST client for /code and /idol."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from urllib.parse import urlencode

from cachetools import TTLCache

from .net import fetch_json, fetch_text, get_breaker
from .resilience import call_with_breaker

log = logging.getLogger(__name__)

BASE = "https://av-wiki.net/wp-json/wp/v2"

# Bounded TTL caches: repeated /code and /idol calls never re-hit the API.
_LOOKUP_CACHE: TTLCache = TTLCache(maxsize=256, ttl=300)
_THUMB_CACHE: TTLCache = TTLCache(maxsize=256, ttl=300)
_TRANSLATE_CACHE: TTLCache = TTLCache(maxsize=512, ttl=86400)
# Bound parallel translations so /idol does not hammer Google with 5 requests
# at once (429 -> breaker -> slower than doing them sequentially).
_TRANSLATE_SEM = asyncio.Semaphore(4)


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


def _dd(description: str, label: str) -> str:
    """Extract the <dd> value that follows a Japanese <dt> label."""
    match = re.search(
        rf"<dt>\s*{re.escape(label)}.*?</dt>\s*<dd>(.*?)</dd>",
        description,
        re.S | re.I,
    )
    return _strip(match.group(1)) if match else ""


def _clean_placeholder(value: str) -> str:
    """av-wiki uses '- - -' for 'not available' — show nothing instead."""
    value = value.strip()
    return "" if not value or set(value) <= set("-–— ") else value


def parse_idol_tag(tag: dict) -> dict:
    """Parse the actress profile embedded in a WordPress tag description."""
    description = str(tag.get("description") or "")
    name = html.unescape(str(tag.get("name") or ""))
    full_name = _dd(description, "AV女優名")

    romaji = ""
    match = re.search(r"[-–—]\s*([A-Za-z][A-Za-z\s'-]+?)\s*$", full_name)
    if match:
        romaji = match.group(1).strip()
    if not romaji:
        kana = re.search(r"[（(]([^）)]+)[）)]", full_name)
        romaji = kana.group(1) if kana else ""

    raw_birth = _dd(description, "生年月日")
    birthdate = raw_birth
    found = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", raw_birth)
    if found:
        birthdate = f"{int(found.group(3)):02d}/{int(found.group(2)):02d}/{found.group(1)}"

    raw_size = _dd(description, "サイズ")
    height = ""
    found_height = re.search(r"T\s*(\d+)", raw_size, re.I)
    if found_height:
        height = f"{found_height.group(1)} cm"
    found_triple = re.search(r"B\s*(\d+)[\s\-–xX]+W\s*(\d+)[\s\-–xX]+H\s*(\d+)", raw_size, re.I)
    measurements = ""
    if found_triple:
        measurements = " / ".join(found_triple.groups())

    image = re.search(r'<img[^>]+src=["\']([^"\']+)', description)

    sns = _dd(description, "SNS")
    # "X： - - - 　Instagram： - - -" means no accounts — hide it.
    if not re.sub(r"(?i)\b(x|instagram|twitter)\b|[:：\s\-\u2013\u2014]", "", sns):
        sns = ""

    return {
        "name": name,
        "romaji": romaji,
        "birthdate": birthdate,
        "height": height,
        "measurements": measurements or _clean_placeholder(raw_size),
        # av-wiki tag payload does not expose birthplace or hobbies.
        "origin": "",
        "hobbies": "",
        "alias": _clean_placeholder(_dd(description, "別名義")),
        "sns": sns,
        "image": image.group(1) if image else "",
        "link": str(tag.get("link", "")),
        "count": tag.get("count", 0),
    }


async def page_thumbnail(link: str) -> str:
    """Read the cover image from the article header of an av-wiki post.

    The WP REST ``content.rendered`` field does not contain the cover — it
    lives in ``<div class="article-thumbnail">`` of the rendered page. Fetching
    that page keeps us in sync with av-wiki's own layout instead of guessing
    CDN URL templates per studio.
    """
    if not link.startswith(("http://", "https://")):
        return ""
    cached = _THUMB_CACHE.get(link)
    if cached is not None:
        return cached

    raw = await fetch_text(link, name="avwiki-page", timeout=15)
    if not raw:
        return ""

    match = re.search(
        r"<div[^>]*class=[\"'][^\"']*article-thumbnail[^\"']*[\"'][^>]*>.*?"
        r"<img[^>]+src=[\"']([^\"']+)",
        raw,
        re.S | re.I,
    )
    if not match:
        return ""
    url = html.unescape(match.group(1))
    if not url.startswith(("http://", "https://")):
        return ""
    _THUMB_CACHE[link] = url
    return url


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

    async with _TRANSLATE_SEM:
        # A sibling coroutine may have populated the cache while we waited.
        cached = _TRANSLATE_CACHE.get(text)
        if cached is not None:
            return cached

        # Google gtx first; MyMemory fallback when Google returns 429/breaker opens.
        url = "https://translate.googleapis.com/translate_a/single?" + urlencode(
            {"client": "gtx", "sl": "auto", "tl": "vi", "dt": "t", "q": text}
        )
        data = await fetch_json(url, name="ja-vi")
        result = ""
        if isinstance(data, list) and data and isinstance(data[0], list):
            result = "".join(str(segment[0]) for segment in data[0] if segment and segment[0])

        if not result:
            source = _guess_source(text)
            fallback_url = "https://api.mymemory.translated.net/get?" + urlencode(
                {"q": text, "langpair": f"{source}|vi"}
            )
            payload = await fetch_json(fallback_url, name="mymemory")
            translated = ((payload or {}).get("responseData") or {}).get("translatedText")
            if translated and "INVALID" not in str(translated).upper():
                result = html.unescape(str(translated))

        if result and result != text:
            _TRANSLATE_CACHE[text] = result
            return result
        return text


_VI_UNIQUE = set("ăâđêôơưĂÂĐÊÔƠƯ")
_VI_TONED = set("ằắẳẵặầấẩẫậềếểễệốồổỗộớờởỡợứừửữự")


def _guess_source(text: str) -> str:
    """Rough script detection for the MyMemory fallback (no extra dependency)."""
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    return "en"


def looks_vietnamese(text: str) -> bool:
    """Skip translation only for clearly Vietnamese text.

    A single 'é'/'ã' is not enough — Portuguese/Spanish would be skipped.
    """
    sample = text[:500]
    if any(char in _VI_UNIQUE for char in sample):
        return True
    return sum(char in _VI_TONED for char in sample) >= 2


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
    result = parse_idol_tag(tag)
    result["works"] = works
    _LOOKUP_CACHE[key] = result
    return result
