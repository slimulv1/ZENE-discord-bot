"""Builders for Discord Components V2 messages."""

from __future__ import annotations

import hashlib

import discord

from .models import ProbeResult

MAX_TEXT = 4000  # total across the whole LayoutView, not per item
# Discord supports 10 items, but with 10 the gallery renders one huge
# full-width item + a 3x3 grid. With 9 it becomes an even 3x3 grid, avoiding
# the oversized, heavily cropped first image that wastes vertical space.
MAX_ITEMS = 9


class CarouselView(discord.ui.LayoutView):
    """Instagram-like carousel: one full-size image with ◀/▶ navigation.

    Discord has no native carousel component for bots. A MediaGallery with a
    single item renders the image at its real aspect ratio (no crop), while
    the action row gives the familiar swipe-like UX without the tall grid.
    """

    def __init__(
        self,
        urls: tuple[str, ...],
        *,
        title: str = "",
        context: str = "",
        spoiler: bool = False,
        hide_quote: bool = False,
    ) -> None:
        super().__init__(timeout=600)
        self.urls = tuple(urls)
        self.index = 0
        self.title = title
        self.context = context
        self.spoiler = spoiler
        self.hide_quote = hide_quote

        key = hashlib.sha256("".join(self.urls).encode("utf-8")).hexdigest()[:12]
        self.container = discord.ui.Container(accent_colour=discord.Colour.blurple())
        self.text = discord.ui.TextDisplay("")
        self.gallery = discord.ui.MediaGallery()
        self.row = discord.ui.ActionRow()
        self.previous = discord.ui.Button(
            emoji="◀",
            style=discord.ButtonStyle.secondary,
            custom_id=f"zene:carousel:{key}:prev",
        )
        self.forward = discord.ui.Button(
            emoji="▶",
            style=discord.ButtonStyle.secondary,
            custom_id=f"zene:carousel:{key}:next",
        )
        self.previous.callback = self._on_previous
        self.forward.callback = self._on_forward
        self.row.add_item(self.previous)
        self.row.add_item(self.forward)
        self.container.add_item(self.text)
        self.container.add_item(self.gallery)
        self.add_item(self.container)
        self.add_item(self.row)
        self._render()

    def _render(self) -> None:
        parts: list[str] = []
        if self.title:
            parts.append(f"**{self.title}**")
        if self.context and not self.hide_quote:
            parts.append(self.context)
        parts.append(f"-# {self.index + 1}/{len(self.urls)}")
        self.text.content = "\n".join(parts)[:MAX_TEXT]

        self.gallery.clear_items()
        self.gallery.add_item(media=self.urls[self.index], spoiler=self.spoiler)

    async def _on_previous(self, interaction, button=None) -> None:
        self.index = (self.index - 1) % len(self.urls)
        self._render()
        await interaction.response.edit_message(view=self)

    async def _on_forward(self, interaction, button=None) -> None:
        self.index = (self.index + 1) % len(self.urls)
        self._render()
        await interaction.response.edit_message(view=self)


def _attach_cta(view: discord.ui.LayoutView, url: str) -> None:
    row = discord.ui.ActionRow(
        discord.ui.Button(style=discord.ButtonStyle.link, label="Xem bài gốc", url=url)
    )
    view.add_item(row)


def build_view(
    result: ProbeResult,
    *,
    spoiler: bool = False,
    hide_quote: bool = False,
    title: str | None = None,
    context: str | None = None,
    send_cta: bool = True,
) -> discord.ui.LayoutView:
    heading = title or result.title
    body = context if context is not None else result.context
    media = result.media_urls[:MAX_ITEMS]

    if result.kind == "gallery" and len(media) > 1:
        view = CarouselView(
            media,
            title=heading or "",
            context=body or "",
            spoiler=spoiler,
            hide_quote=hide_quote,
        )
    else:
        view = discord.ui.LayoutView(timeout=180)
        container = discord.ui.Container(accent_colour=discord.Colour.blurple())

        parts: list[str] = []
        if heading:
            suffix = f" — {result.author}" if result.author else ""
            parts.append(f"**{heading}**{suffix}")
        if body and not hide_quote:
            parts.append(body)
        if parts:
            container.add_item(discord.ui.TextDisplay("\n".join(parts)[:MAX_TEXT]))

        gallery = discord.ui.MediaGallery()
        for url in result.media_urls[:MAX_ITEMS]:
            gallery.add_item(media=url, spoiler=spoiler)
        container.add_item(gallery)
        view.add_item(container)

    if send_cta and result.page_url:
        _attach_cta(view, result.page_url)
    return view


def fallback_text(result: ProbeResult) -> str:
    title = result.title or "Không lấy được nội dung"
    link = result.page_url
    text = f"**{title}**\nKhông lấy được ảnh/video từ link này."
    if link:
        text += f"\n{link}"
    return text[:2000]
