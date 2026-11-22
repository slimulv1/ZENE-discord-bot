"""Today's fuel prices (prefix + slash), from giaxanghomnay.com."""
from __future__ import annotations

import logging
from datetime import date

import discord
from discord.ext import commands

from ..net import fetch_json

log = logging.getLogger(__name__)

API = "https://giaxanghomnay.com/api/pvdate/"


def _collect(obj) -> list[dict]:
    found: list[dict] = []
    if isinstance(obj, dict):
        if "title" in obj and "zone1_price" in obj and "zone2_price" in obj:
            found.append(obj)
        for value in obj.values():
            found.extend(_collect(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_collect(value))
    return found


def _money(value) -> str:
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _trend(value) -> str:
    try:
        change = int(value)
    except (TypeError, ValueError):
        return ""
    if change > 0:
        return " 📈"
    if change < 0:
        return " 📉"
    return ""


def _render(today: date, data) -> discord.Embed:
    # The API returns groups; index 0 is today's price table.
    items = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else data
    rows = [row for row in _collect(items) if isinstance(row, dict)]
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        title = str(row.get("title", ""))
        if title and title not in seen:
            seen.add(title)
            unique.append(row)

    embed = discord.Embed(
        title="⛽ Giá xăng dầu hôm nay",
        description=f"📅 {today.strftime('%d-%m-%Y')}",
        color=0x3498DB,
    )
    for row in unique[:7]:
        embed.add_field(
            name=str(row["title"]),
            value=(
                f"Khu vực 1: **{_money(row['zone1_price'])}đ**"
                f"{_trend(row.get('daily_change'))}\n"
                f"Khu vực 2: **{_money(row['zone2_price'])}đ**"
                f"{_trend(row.get('zone2_daily_change'))}"
            ),
            inline=False,
        )
    if not unique:
        embed.add_field(name="(trống)", value="Không có dữ liệu giá cho ngày này.")
    embed.set_footer(text="Nguồn: Petrolimex")
    return embed


class GiaXang(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="giaxanghomnay", description="Giá xăng hôm nay")
    async def giaxanghomnay(self, ctx: commands.Context) -> None:
        try:
            await ctx.defer()
        except Exception as exc:  # prefix invocation may not need defer at all
            log.debug("defer failed: %s", exc)
        today = date.today()
        data = await fetch_json(API + today.strftime("%Y-%m-%d"), name="giaxang")
        if data is None:
            await self.bot.safe_send(ctx, "Không lấy được giá xăng lúc này, thử lại sau.")
            return
        await self.bot.safe_send(ctx, embed=_render(today, data))


async def setup(bot) -> None:
    await bot.add_cog(GiaXang(bot))
