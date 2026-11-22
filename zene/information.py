import logging
import random

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class information(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="info")
    async def info(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            await ctx.send("Muốn xem info của ai thì tag tên vào")
            return
        try:
            if member.id == 262844868919951360:
                sex0 = "Nam"
                economic0 = "Cần tiền ủng hộ"
            elif member.id == 797507405587677185:
                await ctx.send("Yamete kudasai!!!! Oniiiii-chan")
                return
            elif member.id in (323427262194253825, 347588077272694785):
                sex0 = "Không thể xác định"
                economic0 = "Daiza"
            else:
                sex0 = random.choice(["Mail", "Free mail", "Tuesday", "Không thể xác định"])
                economic0 = random.choice(["Daiza", "Giàu", "Nghèo", "Cần tiền ủng hộ"])
            await ctx.send(
                f"```Đồng Chí: {member.name}\nGiới Tính: {sex0}\nTrạng Thái: {economic0}```"
            )
        except discord.HTTPException as exc:
            log.warning("info send failed: %s", exc)


async def setup(bot):
    await bot.add_cog(information(bot))
