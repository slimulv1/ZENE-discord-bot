"""av-wiki.net WordPress REST client for /code and /idol."""
from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import urlencode

from .net import fetch_json

BASE = "https://av-wiki.net/wp-json/wp/v2"


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
    for candidate in normalize_code(code):
        url = f"{BASE}/posts?{urlencode({'search': candidate, 'per_page': limit})}"
        data = await fetch_json(url, name="avwiki")
        if isinstance(data, list) and data:
            return [parse_post(item) for item in data]
    return []


async def search_idol(name: str, limit: int = 5) -> Optional[dict]:
    tags_url = f"{BASE}/tags?{urlencode({'search': name.strip(), 'per_page': 10})}"
    tags = await fetch_json(tags_url, name="avwiki")
    if not isinstance(tags, list) or not tags:
        return None
    tag = tags[0]
    posts_url = f"{BASE}/posts?{urlencode({'tags': tag['id'], 'per_page': limit})}"
    posts = await fetch_json(posts_url, name="avwiki")
    works = [parse_post(item) for item in posts] if isinstance(posts, list) else []
    return {
        "name": html.unescape(str(tag.get("name", ""))),
        "link": str(tag.get("link", "")),
        "count": tag.get("count", 0),
        "works": works,
    }
