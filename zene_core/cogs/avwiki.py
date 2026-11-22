"""NSFW-only /code and /idol commands backed by av-wiki.net REST API."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..avwiki import (
    bilingual,
    clean_title,
    dmm_image,
    search_code,
    search_idol,
    to_vietnamese,
)

NOT_NSFW = "Lệnh này chỉ dùng được trong kênh NSFW."


def _clip(text: str, size: int = 900) -> str:
    return text if len(text) <= size else text[: size - 3] + "..."


class AvWikiCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        # Mark the slash form NSFW; the prefix form is gated at runtime below.
        self.code.app_command.nsfw = True
        self.idol.app_command.nsfw = True

    @commands.hybrid_command(
        name="code",
        description="Tra cứu phim theo mã (chỉ kênh NSFW)",
    )
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def code(self, ctx: commands.Context, *, arg: str) -> None:
        try:
            await ctx.defer()
        except Exception:
            pass
        channel = getattr(ctx, "channel", None)
        if channel is None or not channel.is_nsfw():
            await self.bot.safe_send(ctx, NOT_NSFW)
            return
        results = await search_code(arg)
        if not results:
            await self.bot.safe_send(ctx, f"Không tìm thấy mã `{arg}` trên av-wiki.")
            return

        item = results[0]
        jp_title = clean_title(item["title"])
        vi_title = await to_vietnamese(jp_title)

        embed = discord.Embed(
            title=f"🎬 Mã phim: {item['code'] or arg.upper()}",
            url=item["link"] or None,
            description=_clip(bilingual(jp_title, vi_title), 700) or None,
            color=discord.Colour.blurple(),
        )

        actress_jp = item["actress"]
        actress_vi = await to_vietnamese(actress_jp) if actress_jp else ""
        fields = [
            ("👩 Diễn viên", bilingual(actress_jp, actress_vi)),
            ("🏢 Hãng sản xuất", item["maker"]),
            ("🏷️ Nhãn", item["label"]),
            ("📼 Series", item["series"]),
            ("🔢 FANZA", item["fanza"]),
            ("📅 Ngày phát hành", item["date"]),
        ]
        for name, value in fields:
            if value:
                embed.add_field(name=name, value=_clip(str(value), 200), inline=True)

        image = item["image"]
        source_note = "Nguồn: av-wiki.net"
        if not image.startswith(("http://", "https://")):
            image = await dmm_image(
                item["code"] or arg,
                self.bot.config.dmm_api_id,
                self.bot.config.dmm_affiliate_id,
            )
            if image:
                source_note += " • Ảnh: FANZA"
        if image.startswith(("http://", "https://")):
            embed.set_image(url=image)
        embed.set_footer(text=source_note)
        await self.bot.safe_send(ctx, embed=embed)

    @commands.hybrid_command(
        name="idol",
        description="Tra cứu diễn viên (chỉ kênh NSFW)",
    )
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def idol(self, ctx: commands.Context, *, arg: str) -> None:
        try:
            await ctx.defer()
        except Exception:
            pass
        channel = getattr(ctx, "channel", None)
        if channel is None or not channel.is_nsfw():
            await self.bot.safe_send(ctx, NOT_NSFW)
            return
        result = await search_idol(arg)
        if result is None:
            await self.bot.safe_send(ctx, f"Không tìm thấy diễn viên `{arg}` trên av-wiki.")
            return

        name_jp = result["name"]
        name_vi = await to_vietnamese(name_jp)
        embed = discord.Embed(
            title=f"🌟 {name_vi or name_jp}",
            url=result["link"] or None,
            description=(
                f"{bilingual(name_jp, name_vi)}\n\n"
                f"📚 Tổng **{result['count']}** tác phẩm được ghi nhận."
            ),
            color=discord.Colour.blurple(),
        )
        for work in result["works"][:4]:
            jp = clean_title(work["title"])
            vi = await to_vietnamese(jp)
            embed.add_field(
                name=f"🎞️ {work['code'] or '—'}",
                value=_clip(bilingual(jp, vi), 240),
                inline=False,
            )
        if not result["works"]:
            embed.add_field(name="(trống)", value="Không lấy được danh sách tác phẩm.")
        embed.set_footer(text="Nguồn: av-wiki.net")
        await self.bot.safe_send(ctx, embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(AvWikiCog(bot))
