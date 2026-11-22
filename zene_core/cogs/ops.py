"""Operator-facing health and lifecycle commands (owner-only where dangerous)."""
from __future__ import annotations

import logging
import math
import time

from discord.ext import commands

log = logging.getLogger(__name__)


class OpsCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.command(name="health")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def health(self, ctx: commands.Context) -> None:
        bot = self.bot
        uptime = int(time.monotonic() - bot.started_at)
        raw_latency = bot.latency
        latency = round(raw_latency * 1000) if math.isfinite(raw_latency) else -1
        lines = [
            "**Zene Health**",
            f"ready: `{bot.is_ready()}` | ping: `{latency}ms` | uptime: `{uptime}s`",
            f"guilds: `{len(bot.guilds)}` | triggers loaded: `{len(bot.triggers)}`",
            f"asset commands: `{bot.assets.command_count}` | restarts: `{bot.state.restarts}`",
            f"extensions failed: `{len(bot.failed_extensions)}`",
        ]
        await self.bot.safe_send(ctx, "\n".join(lines))

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
