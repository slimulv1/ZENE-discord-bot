"""Operator-facing health and lifecycle commands (owner-only where dangerous)."""

from __future__ import annotations

import contextlib
import logging
import math
import time

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class OpsCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="health", description="Xem bot có khỏe không")
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def health(self, ctx: commands.Context) -> None:
        with contextlib.suppress(discord.HTTPException, discord.ClientException):
            await ctx.defer()

        bot = self.bot
        uptime = max(1, int(time.monotonic() - bot.started_at))
        raw_latency = bot.latency
        latency = round(raw_latency * 1000) if math.isfinite(raw_latency) else -1
        failed = sorted(bot.failed_extensions)
        missing = bot.stats.get("missing_assets", 0)
        healthy = bot.is_ready() and not failed and not missing

        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed = discord.Embed(
            title="✅ Zene Bot đang khỏe" if healthy else "⚠️ Zene Bot cần kiểm tra",
            description="Tình trạng hiện tại của bot",
            color=discord.Colour.green() if healthy else discord.Colour.orange(),
        )
        fields = [
            ("⏱️ Uptime", f"{hours}g {minutes}p {seconds}s", True),
            ("📶 Ping", f"{latency} ms" if latency >= 0 else "—", True),
            ("🔁 Khởi động lại", str(bot.state.restarts), True),
            ("🏛️ Server", str(len(bot.guilds)), True),
            ("🎯 Trigger", str(len(bot.triggers)), True),
            ("🎬 Lệnh asset", str(bot.assets.command_count), True),
            (
                "🧩 Extension lỗi",
                "\n".join(f"`{name}`" for name in failed[:8]) or "Không có",
                False,
            ),
            ("🖼️ Asset thiếu", str(missing), True),
        ]
        for name, value, inline in fields:
            embed.add_field(name=name, value=value[:1024], inline=inline)
        embed.set_footer(text="Xem chi tiết tại http://localhost:8080/")
        await self.bot.safe_send(ctx, embed=embed)

    @commands.command(name="stats")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def stats(self, ctx: commands.Context) -> None:
        stats = dict(self.bot.stats) or {"(chưa có sự kiện nào)": 0}
        detail = "\n".join(f"  {key}: {value}" for key, value in sorted(stats.items()))
        await self.bot.safe_send(ctx, f"```\n{detail}\n```")

    @commands.command(name="extensions")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def extensions(self, ctx: commands.Context) -> None:
        loaded = sorted(set(self.bot.extensions))
        text = "loaded: " + ", ".join(loaded)
        if self.bot.failed_extensions:
            text += "\nfailed: " + ", ".join(
                f"{name} ({reason})" for name, reason in self.bot.failed_extensions.items()
            )
        if len(text) > 1900:
            text = text[:1900] + "..."
        await self.bot.safe_send(ctx, f"```{text}```")

    @commands.command(name="reload")
    @commands.is_owner()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        ok, message = await self.bot.reload_extension_safely(extension)
        log.info("reload %s: %s", extension, ok)
        await self.bot.safe_send(ctx, message)

    @commands.command(name="restart")
    @commands.is_owner()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def restart(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, "🫡 わかりました、ご主人様。")
        self.bot.state.restart_requested = True
        await self.bot.close()

    @commands.command(name="shutdown")
    @commands.is_owner()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def shutdown(self, ctx: commands.Context) -> None:
        await self.bot.safe_send(ctx, "Đang tắt bot an toàn...")
        self.bot.state.shutdown_requested = True
        await self.bot.close()


async def setup(bot) -> None:
    await bot.add_cog(OpsCog(bot))
