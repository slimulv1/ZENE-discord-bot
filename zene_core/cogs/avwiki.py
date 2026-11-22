"""NSFW-only /code and /idol commands backed by av-wiki.net REST API."""
from __future__ import annotations

import discord
from discord.ext import commands

from ..avwiki import search_code, search_idol

NOT_NSFW = "Lệnh này chỉ dùng được trong kênh NSFW."


def _clip(text: str, size: int = 900) -> str:
    return text if len(text) <= size else text[: size - 3] + "..."


class AvWikiCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.command(name="code")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def code(self, ctx: commands.Context, *, arg: str) -> None:
        if not ctx.channel.is_nsfw():
            await self.bot.safe_send(ctx, NOT_NSFW)
            return
        results = await search_code(arg)
        if not results:
            await self.bot.safe_send(ctx, f"Không tìm thấy mã `{arg}` trên av-wiki.")
            return
        item = results[0]
        embed = discord.Embed(
            title=item["code"] or arg.upper(),
            url=item["link"] or None,
            description=_clip(item["title"]) or None,
            color=discord.Colour.blurple(),
        )
        for name, key in (
            ("Diễn viên", "actress"),
            ("Hãng", "maker"),
            ("Nhãn", "label"),
            ("Series", "series"),
            ("FANZA", "fanza"),
            ("Ngày phát hành", "date"),
        ):
            if item.get(key):
                embed.add_field(name=name, value=_clip(item[key], 200), inline=True)
        if item["image"].startswith(("http://", "https://")):
            embed.set_image(url=item["image"])
        await self.bot.safe_send(ctx, embed=embed)

    @commands.command(name="idol")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def idol(self, ctx: commands.Context, *, arg: str) -> None:
        if not ctx.channel.is_nsfw():
            await self.bot.safe_send(ctx, NOT_NSFW)
            return
        result = await search_idol(arg)
        if result is None:
            await self.bot.safe_send(ctx, f"Không tìm thấy diễn viên `{arg}` trên av-wiki.")
            return
        embed = discord.Embed(
            title=result["name"],
            url=result["link"] or None,
            description=f"Tổng {result['count']} tác phẩm được ghi nhận.",
            color=discord.Colour.blurple(),
        )
        for work in result["works"]:
            embed.add_field(
                name=work["code"] or "—",
                value=_clip(work["title"], 180),
                inline=False,
            )
        if not result["works"]:
            embed.add_field(name="(trống)", value="Không lấy được danh sách tác phẩm.")
        await self.bot.safe_send(ctx, embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(AvWikiCog(bot))
