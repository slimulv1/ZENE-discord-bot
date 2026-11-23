"""URL validation, canonicalisation and SSRF guard for the embed fixer."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from collections.abc import Iterable

import tldextract
from yarl import URL

from ..net import get_session

log = logging.getLogger(__name__)

SHORTENERS = frozenset({"t.co", "bit.ly", "vm.tiktok.com", "vt.tiktok.com"})
TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = frozenset(
    {
        "igshid",
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "mc_cid",
        "mc_eid",
        "ref",
        "s",
        "spm",
        "si",
        "feature",
        "share",
        "st",
    }
)
# Known public CDN suffixes. Extend as needed; never allow private IPs.
ASSET_SUFFIXES = (
    ".twimg.com",
    ".cdninstagram.com",
    ".tiktokcdn.com",
    ".tiktokcdn-us.com",
    ".ytimg.com",
    ".fbcdn.net",
    ".reddit.com",
    ".blrimg.com",
)


def registrable(host: str) -> str:
    parts = tldextract.extract(host)
    suffix = parts.suffix.lower().strip(".")
    return f"{parts.domain.lower()}.{suffix}" if suffix else parts.domain.lower()


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith(TRACKING_PREFIXES) or lowered in TRACKING_KEYS


async def _resolve_short(url: URL, timeout: float) -> URL:
    session = await get_session()
    async with session.head(
        str(url), allow_redirects=True, max_redirects=3, timeout=timeout
    ) as response:
        return URL(str(response.url))


async def canonicalize(
    raw: str,
    allowed_domains: Iterable[str],
    *,
    timeout: float = 10.0,
    _depth: int = 0,
) -> str:
    """Validate and normalise a user-supplied URL.

    Raises ``ValueError`` when the scheme/host is unsafe or not allowlisted.
    """
    if _depth > 2:
        raise ValueError("too many shortlink redirects")
    url = URL(raw)
    if url.scheme not in {"http", "https"} or url.host is None:
        raise ValueError("invalid scheme or host")
    host = url.host.lower().rstrip(".").removeprefix("www.")

    if host in SHORTENERS:
        final = await _resolve_short(url, timeout)
        return await canonicalize(final, allowed_domains, timeout=timeout, _depth=_depth + 1)

    if _is_ip(host):
        raise ValueError("IP literals are not allowed")
    allowed = {item.lower().lstrip(".") for item in allowed_domains if item}
    if registrable(host) not in allowed:
        raise ValueError(f"domain not allowed: {host}")

    query = [(key, value) for key, value in url.query.items() if not _tracking(key)]
    clean = url.with_host(host).with_query(query).with_fragment(None)
    return str(clean)


def is_asset_url(url: str, allowed_domains: Iterable[str]) -> bool:
    """Accept only direct https asset URLs (or attachment://) for MediaGallery."""
    if url.startswith("attachment://"):
        return True
    try:
        parsed = URL(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.host is None:
        return False
    host = parsed.host.lower().rstrip(".")
    if _is_ip(host):
        return False
    allowed = {item.lower().lstrip(".") for item in allowed_domains if item}
    return registrable(host) in allowed or host.endswith(ASSET_SUFFIXES)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
