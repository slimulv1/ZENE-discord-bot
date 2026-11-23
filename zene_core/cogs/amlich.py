"""Lunar calendar command (prefix + slash)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import date, datetime, timedelta, timezone

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


def _conflict_lines(conflict: dict, year: int) -> list[str]:
    """Show the full lục-xung (same-branch) cycle plus vnlunar's confirmed ages.

    ``direction.py:56-64`` only lists Can-Chi whose Nạp Âm khắc the day's, so
    its list is a strict subset of the 12-year same-branch cycle. We keep the
    full cycle the user asked for, mark the exact confirmed ages and append any
    rule-(B) "xung phụ" ages that share the *day's* branch.
    """
    import vnlunar

    library_ages = conflict.get("conflicting_ages") or []
    chi = conflict.get("conflict_chi") or ""
    if not chi and library_ages and isinstance(library_ages[0], dict):
        chi = str(library_ages[0].get("chi") or "")

    # Key by (age, can_chi): the same Can-Chi repeats every 60 years, but only
    # the specific age returned by vnlunar is confirmed (e.g. 23, not 83).
    confirmed: dict[str, str] = {}
    for item in library_ages:
        if isinstance(item, dict):
            confirmed[str(item.get("age", ""))] = str(item.get("can_chi", "")).replace("*", "").strip()

    if chi and library_ages:
        lines: list[str] = []
        listed_ages: set[str] = set()
        for birth in range(year - 1, year - 101, -1):
            name = str(vnlunar.get_year_can_chi(birth))
            if not name.endswith(chi):
                continue
            age = year - birth
            listed_ages.add(str(age))
            marker = " (*)" if confirmed.get(str(age)) == name else ""
            lines.append(f"Tuổi {age} : {name}{marker}")

        # Rule (B) entries use the day's chi, so they are not in the cycle above.
        for age, name in confirmed.items():
            if age not in listed_ages:
                lines.append(f"Tuổi {age} : {name} (*) [xung phụ]")
        return lines

    return []  # no library-confirmed conflict -> do not invent one


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

    # get_full_info uses lunar['year'] for ages (vnlunar/__init__.py:209).
    # Using the solar year shifts every age by 1 before Tết. Reuse the payload
    # that get_full_info already prepared so both agree.
    lunar_year = lunar.get("year", year)
    conflict = info.get("conflicting_ages") or vnlunar.get_conflicting_ages(jd, lunar_year) or {}
    conflict_lines = _conflict_lines(conflict, lunar_year)

    hour_lines = _normalize_hours(vnlunar.get_auspicious_hours(jd))

    embed = discord.Embed(
        title=(
            f"📅 Âm lịch {lunar.get('day', '')}-{lunar.get('month', '')}-{lunar.get('year', '')}"
            f"{' (nhuận)' if lunar.get('leap') == 1 else ''}"
        ),
        description=_emojize(description),
        color=0x3498DB,
    )
    # 12_stars.description mixes good and bad advice ("kỵ ..."), so labelling
    # it "Phù hợp" is misleading. Prefer the explicit good_for/bad_for lists.
    truc = info.get("12_constructions", {}) or {}
    good = ", ".join(str(item) for item in (truc.get("good_for") or []))
    bad = ", ".join(str(item) for item in (truc.get("bad_for") or []))
    if good or bad:
        work_value = f"✅ Nên: {good or '—'}\n🚫 Kỵ: {bad or '—'}"
    else:
        work_value = str((info.get("12_stars") or {}).get("description") or "")
    embed.add_field(
        name=f"☯️ {truc.get('name') or 'Trực trong ngày'} - nên/kỵ",
        value=_clip(work_value) or "Không có thông tin",
        inline=False,
    )
    embed.add_field(
        name="🚫 Tuổi Xung (Lục xung - cùng chi)",
        value=_clip(
            (
                "\n".join(conflict_lines)
                + "\n(*) Xung theo Nạp Âm (vnlunar); [xung phụ] cùng chi ngày"
            )
            if conflict_lines
            else "Không có thông tin"
        ),
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
            # Pin to Vietnam time (UTC+7) — vnlunar assumes time_zone=7.0.
            # date.today() would use the host's zone and can show the wrong day
            # on machines running in UTC.
            vietnam_today = datetime.now(timezone(timedelta(hours=7))).date()
            embed = await asyncio.to_thread(_render, vietnam_today)
        except Exception as exc:  # noqa: BLE001 - vnlunar can raise many shapes
            await self.bot.safe_send(ctx, f"Không lấy được âm lịch: {exc}")
            return
        await self.bot.safe_send(ctx, embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(AmLich(bot))
