"""Lunar calendar command (prefix + slash)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import date

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

ZODIAC_EMOJI = {
    "Tý": "🐁",
    "Sửu": "🐃",
    "Dần": "🐅",
    "Mão": "🐈",
    "Thìn": "🐉",
    "Tỵ": "🐍",
    "Ngọ": "🐎",
    "Mùi": "🐐",
    "Thân": "🐒",
    "Dậu": "🐤",
    "Tuất": "🐕",
    "Hợi": "🐖",
}


def _clip(text: str, size: int = 1000) -> str:
    return text if len(text) <= size else text[: size - 3] + "..."


def _emojize(text: str) -> str:
    for key, emoji in ZODIAC_EMOJI.items():
        text = text.replace(key, emoji)
    return text


def _emojize_keep(text: str) -> str:
    """Add the zodiac emoji next to the name instead of replacing the word."""
    for key, emoji in ZODIAC_EMOJI.items():
        if key in text:
            text = text.replace(key, f"{emoji} {key}")
    return text


def _normalize_hours(hours) -> list[str]:
    """Turn vnlunar's auspicious-hours payload into readable lines.

    Depending on the vnlunar version this is a comma-separated ``str`` (the
    common case), a dict wrapping a list, or a list of dicts. Iterating the raw
    string directly would put every single character on its own Discord line.
    """
    if isinstance(hours, str):
        chunks: list = re.split(r"[,;]", hours)
    elif isinstance(hours, dict):
        return _normalize_hours(
            hours.get("hours") or hours.get("auspicious_hours") or hours.get("value") or ""
        )
    elif isinstance(hours, (list, tuple)):
        chunks = []
        for item in hours:
            if isinstance(item, dict):
                label = " ".join(
                    str(item[key])
                    for key in ("hour_name", "hour", "time_range", "time")
                    if item.get(key)
                )
                chunks.append(label.strip())
            else:
                chunks.append(item)
    else:
        chunks = [hours]

    lines: list[str] = []
    for chunk in chunks:
        text = " ".join(str(chunk).split())  # collapse stray newlines/spaces
        if text:
            lines.append(text)
    return lines


def _render(today: date) -> discord.Embed:
    import vnlunar

    day, month, year = today.day, today.month, today.year
    lunar = vnlunar.get_lunar_date(day, month, year)
    info = vnlunar.get_full_info(day, month, year)
    jd = vnlunar.jdn(day, month, year)

    can_chi = info.get("can_chi", {})
    description = (
        f"Ngày {can_chi.get('day', '')}, tháng {can_chi.get('month', '')}, "
        f"năm {can_chi.get('year', '')}"
    )

    conflict = vnlunar.get_conflicting_ages(jd, year) or {}
    ages = conflict.get("conflicting_ages") or conflict.get("ages") or []
    conflict_lines = []
    for item in ages[:8]:
        if isinstance(item, dict):
            age = item.get("age", "")
            chi = item.get("can_chi", "")
            animal = item.get("animal", "")
            conflict_lines.append(f"Tuổi {age}: {chi} {animal}".strip())
        else:
            conflict_lines.append(str(item))

    hour_lines = _normalize_hours(vnlunar.get_auspicious_hours(jd))

    embed = discord.Embed(
        title=f"📅 {lunar.get('day', '')}-{lunar.get('month', '')}-{lunar.get('year', '')}",
        description=_emojize(description),
        color=0x3498DB,
    )
    embed.add_field(
        name="✅ Phù hợp",
        value=_clip(info.get("12_stars", {}).get("description", "") or "Không có thông tin"),
        inline=False,
    )
    embed.add_field(
        name="🚫 Tuổi xung",
        value=_clip("\n".join(conflict_lines) or "Không có thông tin"),
        inline=False,
    )
    embed.add_field(
        name="🌟 Giờ Hoàng Đạo",
        value=_clip(_emojize_keep("\n".join(hour_lines)) or "Không có thông tin"),
        inline=False,
    )
    embed.set_footer(text=f"Dương lịch: {today.strftime('%d-%m-%Y')}")
    return embed


class AmLich(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="amlich", description="Âm lịch hôm nay")
    @app_commands.checks.cooldown(1, 5)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def amlich(self, ctx: commands.Context) -> None:
        with contextlib.suppress(discord.HTTPException, discord.ClientException):
            await ctx.defer()
        try:
            embed = await asyncio.to_thread(_render, date.today())
        except Exception as exc:  # noqa: BLE001 - vnlunar can raise many shapes
            await self.bot.safe_send(ctx, f"Không lấy được âm lịch: {exc}")
            return
        await self.bot.safe_send(ctx, embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(AmLich(bot))
