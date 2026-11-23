"""/code and /idol commands backed by av-wiki.net REST API.

NSFW channel gating is controlled by ``ZENE_NSFW_ENABLED``. /code images are
always blurred and sent as spoiler attachments regardless of that setting.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from io import BytesIO

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
from ..net import get_session

log = logging.getLogger(__name__)

NOT_NSFW = "Lệnh này chỉ dùng được trong kênh NSFW."


async def _blurred_file(url: str) -> discord.File | None:
    """Fetch an image and return it blurred as a spoiler attachment."""
    from PIL import Image, ImageFilter

    try:
        session = await get_session()
        async with session.get(url, timeout=15) as response:
            response.raise_for_status()
            raw = await response.read()

        def blur() -> BytesIO:
            with Image.open(BytesIO(raw)) as image:
                result = image.convert("RGB").filter(ImageFilter.GaussianBlur(12))
                out = BytesIO()
                result.save(out, format="JPEG", quality=82)
                out.seek(0)
                return out

        return discord.File(await asyncio.to_thread(blur), filename="code.jpg", spoiler=True)
    except Exception as exc:  # noqa: BLE001 - image is optional; keep the text result
        log.warning("không làm mờ được ảnh /code: %s", exc)
        return None


def _clip(text: str, size: int = 900) -> str:
    return text if len(text) <= size else text[: size - 3] + "..."


class AvWikiCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        # Discord-side NSFW marker follows the operator setting.
        self.code.app_command.nsfw = bot.config.nsfw_enabled
        self.idol.app_command.nsfw = bot.config.nsfw_enabled

    @commands.hybrid_command(
        name="code",
        description="Tra cứu phim theo mã (chỉ kênh NSFW)",
    )
    @app_commands.describe(arg="Mã phim cần tra, ví dụ SONE-192")
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def code(self, ctx: commands.Context, *, arg: str) -> None:
        with contextlib.suppress(discord.HTTPException, discord.ClientException):
            await ctx.defer()
        channel = getattr(ctx, "channel", None)
        if self.bot.config.nsfw_enabled and (channel is None or not channel.is_nsfw()):
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

        attachment = None
        if image.startswith(("http://", "https://")):
            attachment = await _blurred_file(image)
            if attachment is not None:
                embed.set_image(url=f"attachment://{attachment.filename}")
                source_note += " • ảnh đã làm mờ"
        embed.set_footer(text=source_note)
        if attachment is None:
            await self.bot.safe_send(ctx, embed=embed)
        else:
            await self.bot.safe_send(ctx, embed=embed, file=attachment)

    @commands.hybrid_command(
        name="idol",
        description="Tra cứu diễn viên (chỉ kênh NSFW)",
    )
    @app_commands.describe(arg="Tên diễn viên cần tra")
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def idol(self, ctx: commands.Context, *, arg: str) -> None:
        with contextlib.suppress(discord.HTTPException, discord.ClientException):
            await ctx.defer()
        channel = getattr(ctx, "channel", None)
        if self.bot.config.nsfw_enabled and (channel is None or not channel.is_nsfw()):
            await self.bot.safe_send(ctx, NOT_NSFW)
            return
        result = await search_idol(arg)
        if result is None:
            await self.bot.safe_send(ctx, f"Không tìm thấy diễn viên `{arg}` trên av-wiki.")
            return

        name_jp = result["name"]
        romaji = result.get("romaji") or ""
        embed = discord.Embed(
            title=f"🌟 {name_jp}{f' 【{romaji}】' if romaji else ''}",
            url=result["link"] or None,
            description=f"📚 Tổng **{result['count']}** tác phẩm được ghi nhận.",
            color=discord.Colour.blurple(),
        )
        if result.get("image"):
            embed.set_thumbnail(url=result["image"])

        # Profile fields shown in the reference card. av-wiki only provides
        # some of them; missing values are shown as a dash, never invented.
        profile = (
            ("🏠 Đến từ", result.get("origin")),
            ("📏 Số đo 3 vòng", result.get("measurements")),
            ("📐 Chiều cao", result.get("height")),
            ("🎂 Ngày sinh", result.get("birthdate")),
            ("💚 Sở thích", result.get("hobbies")),
            ("🔤 Tên khác", result.get("alias")),
            ("📱 SNS", result.get("sns")),
        )
        for label, value in profile:
            embed.add_field(name=label, value=_clip(value or "—", 200), inline=True)

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
