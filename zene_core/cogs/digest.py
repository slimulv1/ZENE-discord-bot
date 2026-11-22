"""Optional daily digest (idea from AlphaCore/wakeup.py, fully config-driven)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands

from ..net import fetch_json

log = logging.getLogger(__name__)

GIAXANG_API = "https://giaxanghomnay.com/api/pvdate/"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Không tìm thấy timezone %s, dùng UTC", name)
        return ZoneInfo("UTC")


def _gas_price(data) -> str:
    rows = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else data
    found: list[dict] = []

    def walk(obj) -> None:
        if isinstance(obj, dict):
            if "title" in obj and "zone1_price" in obj:
                found.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(rows)
    for row in found:
        if "E10 RON 95" in str(row["title"]):
            try:
                return f"{int(row['zone1_price']):,}đ/lít".replace(",", ".")
            except (TypeError, ValueError):
                break
    return "(chưa có dữ liệu)"


class DigestCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        if not self.bot.config.digest_channel_id:
            log.info("daily digest tắt (ZENE_DIGEST_CHANNEL_ID=0)")
            return
        self._task = asyncio.create_task(self._loop())
        log.info(
            "daily digest: channel=%d lúc %02d:%02d (%s)",
            self.bot.config.digest_channel_id,
            self.bot.config.digest_hour,
            self.bot.config.digest_minute,
            self.bot.config.digest_timezone,
        )

    async def cog_unload(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _seconds_until_next(self) -> float:
        cfg = self.bot.config
        now = datetime.now(_zone(cfg.digest_timezone))
        next_run = now.replace(
            hour=cfg.digest_hour, minute=cfg.digest_minute, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return max(1.0, (next_run - now).total_seconds())

    async def _loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(self._seconds_until_next())
            try:
                await self._send()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - scheduler boundary
                log.warning("daily digest failed: %s", exc)

    async def _send(self) -> None:
        cfg = self.bot.config
        channel = self.bot.get_channel(cfg.digest_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(cfg.digest_channel_id)
            except (discord.HTTPException, discord.Forbidden) as exc:
                log.warning("Không lấy được kênh digest: %s", exc)
                return

        today = datetime.now(_zone(cfg.digest_timezone)).date()
        from .amlich import _render as render_amlich

        lunar = await asyncio.to_thread(render_amlich, today)
        embed = discord.Embed(
            title="⏰ Chào buổi sáng",
            description=f"📅 {today.strftime('%d-%m-%Y')}",
            color=discord.Colour.green(),
        )
        if len(lunar.fields) > 0:
            embed.add_field(name=lunar.fields[0].name, value=lunar.fields[0].value, inline=False)
        if len(lunar.fields) > 2:
            embed.add_field(name=lunar.fields[2].name, value=lunar.fields[2].value, inline=False)
        data = await fetch_json(GIAXANG_API + today.strftime("%Y-%m-%d"), name="giaxang")
        embed.add_field(name="⛽ Giá xăng", value=_gas_price(data), inline=False)
        embed.set_footer(text="Nguồn: vnlunar • Petrolimex")

        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await channel.send(
                content="@everyone" if cfg.digest_ping else None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=cfg.digest_ping),
            )


async def setup(bot) -> None:
    await bot.add_cog(DigestCog(bot))
