"""Builders for Discord Components V2 messages."""

from __future__ import annotations

import discord

from .models import ProbeResult

MAX_TEXT = 4000  # total across the whole LayoutView, not per item
# Discord supports 10 items, but with 10 the gallery renders one huge
# full-width item + a 3x3 grid. With 9 it becomes an even 3x3 grid, avoiding
# the oversized, heavily cropped first image that wastes vertical space.
MAX_ITEMS = 9


def build_view(
    result: ProbeResult,
    *,
    spoiler: bool = False,
    hide_quote: bool = False,
    title: str | None = None,
    context: str | None = None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    container = discord.ui.Container(accent_colour=discord.Colour.blurple())

    parts: list[str] = []
    heading = title or result.title
    if heading:
        suffix = f" — {result.author}" if result.author else ""
        parts.append(f"**{heading}**{suffix}")
    body = context if context is not None else result.context
    if body and not hide_quote:
        parts.append(body)
    if parts:
        container.add_item(discord.ui.TextDisplay("\n".join(parts)[:MAX_TEXT]))

    gallery = discord.ui.MediaGallery()
    for url in result.media_urls[:MAX_ITEMS]:
        gallery.add_item(media=url, spoiler=spoiler)
    container.add_item(gallery)
    view.add_item(container)
    return view


def fallback_text(result: ProbeResult) -> str:
    title = result.title or "Không lấy được nội dung"
    link = result.page_url
    text = f"**{title}**\nKhông lấy được ảnh/video từ link này."
    if link:
        text += f"\n{link}"
    return text[:2000]
