"""Domain-based adapter routing — avoids fetching pages we do not need."""

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
