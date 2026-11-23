"""Data models for the link embedder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import discord


@dataclass(frozen=True, slots=True)
class LinkContext:
    message: discord.Message
    raw_url: str
    canonical: str
    modifiers: frozenset[str] = field(default_factory=frozenset)
    lang: str | None = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    kind: Literal["image", "video", "gallery", "none"]
    title: str
    author: str
    media_urls: tuple[str, ...] = ()
    context: str = ""
    # None = unknown. Strict mode treats unknown as NSFW.
    nsfw: bool | None = None
    page_url: str = ""

    @property
    def has_media(self) -> bool:
        return bool(self.media_urls)
