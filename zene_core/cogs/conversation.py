"""Safe replacement for the legacy ``communicate`` cog.

Fixes: no pandas on the message hot path, no self-trigger loops, no shared
cache file, bounded concurrency, per-user cooldowns and total error containment.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..content import ANXIN_STORIES, COMMAND_TEXTS
from ..triggers import Response, normalize

log = logging.getLogger(__name__)


class ConversationCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self._rng = random.SystemRandom()
        default = max(0.1, bot.config.trigger_cooldown)
        self._cooldowns = {
            trigger.name: commands.CooldownMapping.from_cooldown(
                1,
                trigger.cooldown if trigger.cooldown > 0 else default,
                commands.BucketType.user,
            )
            for trigger in bot.triggers.all
        }
        self._excel_cooldowns: dict[str, commands.CooldownMapping] = {}
        self._excel_cooldown_default = default

    # ------------------------------------------------------------- listener --
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self.bot.config.ignore_bots and message.author.bot:
            return
        if self.bot.state.shutdown_requested:
            return

        content = message.content or ""
        if not content.strip():
            return

        match = self.bot.triggers.match(content)
        if match is not None:
            mapping = self._cooldowns.get(match.trigger.name)
            if mapping is not None and mapping.update_rate_limit(message) is not None:
                return
            self.bot.stats["trigger_hits"] += 1
            await self._deliver(message, match.trigger.payload)
            return

        # Excel-derived asset commands: O(1) dict lookup, loaded once at boot.
        relative = self.bot.assets.file_for_command(content)
        if relative is not None:
            key = normalize(content)
            mapping = self._excel_cooldowns.get(key)
            if mapping is None:
                # Bounded cache: arbitrary user text must not grow memory forever.
                if len(self._excel_cooldowns) > 512:
                    self._excel_cooldowns.clear()
                mapping = commands.CooldownMapping.from_cooldown(
                    1, self._excel_cooldown_default, commands.BucketType.user
                )
                self._excel_cooldowns[key] = mapping
            if mapping.update_rate_limit(message) is not None:
                return
            self.bot.stats["excel_hits"] += 1
            await self._deliver(message, Response("file", relative))

    # ------------------------------------------------------------- delivery --
    async def _deliver(self, target, payload: Response) -> None:
        try:
            kind = payload.kind
            if kind == "text":
                await self.bot.safe_send(target, str(payload.value))
            elif kind == "choice":
                await self.bot.safe_send(target, self._rng.choice(payload.value))
            elif kind in {"file", "asset"}:
                await self.bot.send_asset(target, str(payload.value), payload.filename)
            elif kind == "folder":
                relative = self.bot.assets.random_in(str(payload.value))
                if relative is None:
                    await self.bot.safe_send(target, "Asset tạm thời hết hàng rồi :(")
                else:
                    await self.bot.send_asset(target, relative)
            elif kind == "composite":
                spec, user = payload.value
                await self._composite(target, spec, user)
            else:
                log.warning("payload kind không xác định: %s", kind)
        except Exception as exc:  # noqa: BLE001 - never break on_message
            log.error("delivery failed (%s): %s", payload.kind, exc)
            await self.bot.safe_send(target, "Bot đang lag nhẹ, thử lại sau nhé.")

    async def _composite(self, target, spec, user=None) -> None:
        base, box, size, *rest = spec
        mask = rest[0] if rest else None
        author = user or target.author
        avatar = author.avatar or author.display_avatar
        try:
            # Avoid animated GIF frames / palette quirks — always get a static PNG.
            avatar = avatar.with_static_format("png")
        except Exception:
            pass
        avatar_bytes = await avatar.read()
        output = await self.bot.assets.composite_avatar(
            base, avatar_bytes, box, size, mask
        )
        if output is None:
            await self.bot.safe_send(target, "Không xử lý được ảnh lúc này.")
            return
        await self.bot.safe_send(
            target, file=discord.File(output, filename="zene-composite.png")
        )

    # -------------------------------------------------------------- commands --
    @commands.hybrid_command(name="avt", description="Xem ảnh đại diện")
    @app_commands.checks.cooldown(1, 3)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def avt(self, ctx: commands.Context, member: Optional[discord.User] = None) -> None:
        user = member or ctx.author
        avatar = user.avatar or user.display_avatar
        embed = discord.Embed(
            title=f"Ảnh đại diện của {user.display_name}",
            url=avatar.url,
            color=discord.Colour.blurple(),
        )
        try:
            embed.set_image(url=avatar.with_size(512).url)
        except Exception:
            embed.set_image(url=avatar.url)
        await self.bot.safe_send(ctx, embed=embed)

    @commands.hybrid_command(name="haha", description="Ghép avatar vào ảnh haha")
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def haha(self, ctx: commands.Context, member: Optional[discord.User] = None) -> None:
        target = member or ctx.author
        await self._deliver(
            ctx,
            Response(
                "composite",
                (
                    ("zene/data/image/haha.jpg", (470, 120), (256, 256), "ellipse"),
                    target,
                ),
            ),
        )

    @commands.command(name="tv")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def tv(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        await self._deliver(
            ctx,
            Response(
                "composite",
                (
                    ("zene/data/image/tv/FB_IMG_1573133316104.jpg", (95, 115), (100, 100), None),
                    target,
                ),
            ),
        )

    @commands.command(name="bonk")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def bonk(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        if member is not None and member.id in self.bot.owner_ids:
            await self.bot.safe_send(ctx, "Không được đánh Onii-sama :angry:")
            return
        await self._deliver(ctx, Response("folder", "bonk"))

    @commands.command(name="auzam")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def auzam(self, ctx: commands.Context) -> None:
        await self._deliver(ctx, Response("folder", "auzam"))

    @commands.command(name="nohorny")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def nohorny(self, ctx: commands.Context) -> None:
        await self._deliver(ctx, Response("folder", "no_horny"))

    @commands.command(name="wake")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def wake(self, ctx: commands.Context) -> None:
        await self._deliver(ctx, Response("file", "zene/data/video/wake.mp4"))

    @commands.command(name="cmd")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def cmd(self, ctx: commands.Context) -> None:
        names = self.bot.assets.command_names
        text = ", ".join(names) if names else "(chưa nạp được danh sách lệnh)"
        if len(text) > 1900:
            text = text[:1900] + "..."
        await self.bot.safe_send(ctx, f"```{text}```")

    @commands.command(name="hotro")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def hotro(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, COMMAND_TEXTS["hotro"])

    @commands.command(name="xinloi")
    async def xinloi(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, COMMAND_TEXTS["xinloi"])

    @commands.command(name="sapnupuas")
    async def sapnupuas(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, COMMAND_TEXTS["sapnupuas"])

    @commands.command(name="anxin")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def anxin(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, self._rng.choice(ANXIN_STORIES))

    @commands.command(name="samhoi")
    async def samhoi(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, COMMAND_TEXTS["samhoi"])


async def setup(bot) -> None:
    await bot.add_cog(ConversationCog(bot))
