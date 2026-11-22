"""Reusable author-only pagination view (adapted from AlphaCore to discord.py 2.x)."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

PageGetter = Callable[[int], Awaitable[tuple[discord.Embed, int]]]


class Paginator(discord.ui.View):
    """A view that renders pages produced by an async callback.

    Only the user who invoked the command may press the buttons, and buttons
    are removed on timeout so the message never becomes a dead UI.
    """

    def __init__(self, author_id: int, get_page: PageGetter, timeout: float = 180) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.get_page = get_page
        self.index = 1
        self.total = 1
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        with contextlib.suppress(discord.HTTPException):
            await interaction.response.send_message(
                "Chỉ người gọi lệnh mới dùng được các nút này.", ephemeral=True
            )
        return False

    def _sync(self) -> None:
        self.first.disabled = self.index <= 1
        self.previous.disabled = self.index <= 1
        self.next.disabled = self.index >= self.total
        self.last.disabled = self.index >= self.total
        self.indicator.label = f"{self.index}/{self.total}"

    async def _show(self, interaction: discord.Interaction | None) -> None:
        embed, self.total = await self.get_page(self.index)
        self._sync()
        if interaction is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await interaction.response.edit_message(embed=embed, view=self)

    async def send(self, ctx) -> None:
        embed, self.total = await self.get_page(self.index)
        self._sync()
        self.message = await ctx.send(embed=embed, view=self if self.total > 1 else None)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.blurple)
    async def first(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.index = 1
        await self._show(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.blurple)
    async def previous(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.index = max(1, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.grey, disabled=True)
    async def indicator(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        with contextlib.suppress(discord.HTTPException):
            await interaction.response.defer()

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.index = min(self.total, self.index + 1)
        await self._show(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple)
    async def last(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.index = self.total
        await self._show(interaction)

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.message.edit(view=None)


async def paginated_list(
    ctx,
    title: str,
    items: list[str],
    per_page: int = 15,
) -> None:
    """Convenience helper for a simple numbered list."""
    total = max(1, (len(items) + per_page - 1) // per_page)

    async def get_page(page: int) -> tuple[discord.Embed, int]:
        start = (page - 1) * per_page
        chunk = items[start : start + per_page]
        embed = discord.Embed(
            title=title,
            description="\n".join(
                f"{start + offset}. `{name}`" for offset, name in enumerate(chunk, 1)
            )
            or "(trống)",
            color=discord.Colour.blurple(),
        )
        embed.set_footer(text=f"Trang {page}/{total}")
        return embed, total

    await Paginator(ctx.author.id, get_page).send(ctx)
