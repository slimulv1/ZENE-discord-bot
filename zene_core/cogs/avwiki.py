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
    page_thumbnail,
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
        description="Tra cứu phim theo mã (ảnh được làm mờ)",
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
        actress_jp = item["actress"]
        need_page = not item["image"].startswith(("http://", "https://"))

        # All of these are independent: translate title/actress and look up the
        # cover from av-wiki + FANZA concurrently instead of paying 4x RTT.
        tasks = [to_vietnamese(jp_title)]
        if actress_jp:
            tasks.append(to_vietnamese(actress_jp))
        if need_page:
            tasks.append(page_thumbnail(item["link"]))
        tasks.append(
            dmm_image(
                item["code"] or arg,
                self.bot.config.dmm_api_id,
                self.bot.config.dmm_affiliate_id,
            )
        )
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        vi_title = gathered[0] if isinstance(gathered[0], str) else jp_title
        cursor = 1
        actress_vi = ""
        if actress_jp:
            actress_vi = gathered[cursor] if isinstance(gathered[cursor], str) else ""
            cursor += 1
        page_image = ""
        if need_page:
            page_image = gathered[cursor] if isinstance(gathered[cursor], str) else ""
            cursor += 1
        fanza_image = gathered[cursor] if isinstance(gathered[cursor], str) else ""

        embed = discord.Embed(
            title=f"🎬 Mã phim: {item['code'] or arg.upper()}",
            url=item["link"] or None,
            description=_clip(bilingual(jp_title, vi_title), 700) or None,
            color=discord.Colour.blurple(),
        )

        fields = [
            ("👩 Diễn viên", bilingual(actress_jp, actress_vi)),
            ("🏢 Hãng sản xuất", item["maker"]),
            ("🏷️ Nhãn", item["label"]),
            ("📼 Series", item["series"]),
            ("📅 Ngày phát hành", item["date"]),
            ("🔢 FANZA", item["fanza"]),
        ]
        for name, value in fields:
            if value:
                embed.add_field(name=name, value=_clip(str(value), 200), inline=True)

        image = item["image"]
        source_note = "Nguồn: av-wiki.net"
        if not image.startswith(("http://", "https://")) and page_image.startswith(
            ("http://", "https://")
        ):
            image = page_image
            source_note += " • Ảnh: av-wiki"
        if not image.startswith(("http://", "https://")) and fanza_image.startswith(
            ("http://", "https://")
        ):
            image = fanza_image
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
        description="Tra cứu diễn viên (profile + tác phẩm)",
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
        works = result["works"][:4]
        work_titles = [clean_title(work["title"]) for work in works]

        # Translate the name and every work title concurrently; the shared
        # semaphore in to_vietnamese keeps this from spamming the provider.
        translated = await asyncio.gather(
            *(to_vietnamese(text) for text in (name_jp, *work_titles)),
            return_exceptions=True,
        )
        name_vi = translated[0] if isinstance(translated[0], str) else ""
        work_vi = [value if isinstance(value, str) else "" for value in translated[1:]]

        embed = discord.Embed(
            title=f"🌟 {name_jp}{f' 【{romaji or name_vi}】' if (romaji or name_vi) else ''}",
            url=result["link"] or None,
            description=f"📚 Tổng **{result['count']}** tác phẩm được ghi nhận.",
            color=discord.Colour.blurple(),
        )
        if result.get("image"):
            embed.set_thumbnail(url=result["image"])

        # Profile first, ordered like the reference card: identity -> body ->
        # background -> extra. Missing data is shown as a dash, never invented.
        profile = (
            ("🎂 Ngày sinh", result.get("birthdate")),
            ("📐 Chiều cao", result.get("height")),
            ("📏 Số đo 3 vòng", result.get("measurements")),
            ("🏠 Đến từ", result.get("origin")),
            ("💚 Sở thích", result.get("hobbies")),
            ("🔤 Tên khác", result.get("alias")),
            ("📱 SNS", result.get("sns")),
        )
        for label, value in profile:
            embed.add_field(name=label, value=_clip(value or "—", 200), inline=True)

        if works:
            embed.add_field(name="🎬 Tác phẩm gần đây", value="─" * 12, inline=False)
        for work, jp, vi in zip(works, work_titles, work_vi, strict=True):
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
