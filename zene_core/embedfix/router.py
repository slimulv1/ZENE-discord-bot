"""Routing adapter theo domain — tránh fetch trang không cần.

Tiếng Việt: `route_for` chọn adapter theo domain (X→fxtwitter/x-direct/meta,
IG→ifx/oginstagram/meta, FB→facebed/meta, TikTok→tnktok/tikwm/meta).
日本語: ドメイン→アダプタのルーティング。不要なページ取得を避ける。
"""

from __future__ import annotations

from yarl import URL

from .guards import registrable

ROUTES: dict[str, tuple[str, ...]] = {
    "x.com": ("fxtwitter", "x-direct", "meta"),
    "twitter.com": ("fxtwitter", "x-direct", "meta"),
    "instagram.com": ("ifx", "oginstagram", "meta"),
    "facebook.com": ("facebed", "meta"),
    "fb.com": ("facebed", "meta"),
    "tiktok.com": ("tnktok", "tikwm", "meta"),
}

PROXY_ADAPTERS = frozenset(
    {"fxtwitter", "x-direct", "ifx", "oginstagram", "facebed", "tnktok", "tikwm"}
)


def route_for(url: str, use_proxies: bool = True) -> tuple[str, ...]:
    """Return adapter names in priority order for a canonical URL."""
    host = (URL(url).host or "").lower()
    names = ROUTES.get(registrable(host), ("meta",))
    if not use_proxies:
        return ("meta",)
    return names
