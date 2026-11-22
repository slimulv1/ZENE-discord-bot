"""Legacy waifu command (not loaded by default — duplicate of hentai_interact)."""

from discord.ext import commands

from zene_core.net import fetch_json

URL = "https://api.waifu.pics/sfw/waifu"


class Waifu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="waifu")
    async def waifu(self, ctx):
        payload = await fetch_json(URL, name="waifu-api")
        image = payload.get("url") if isinstance(payload, dict) else None
        await ctx.send(image if image else "API tạm thời không khả dụng.")


async def setup(bot):
    await bot.add_cog(Waifu(bot))
