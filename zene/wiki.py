import asyncio
import logging

import wikipedia
from discord.ext import commands

log = logging.getLogger(__name__)


async def wiki_sum(arg):
    def work():
        wikipedia.set_lang("vi")
        return wikipedia.summary(arg, sentences=3)

    # wikipedia performs blocking network I/O — keep it off the event loop.
    return await asyncio.to_thread(work)


class wiki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def wiki(self, ctx, *, arg):
        try:
            await ctx.send(await wiki_sum(arg))
        except Exception as exc:  # noqa: BLE001 - wikipedia SDK boundary
            log.warning("wiki lookup failed: %s", exc)
            await ctx.send("T tìm rồi nhưng ko có. Dùng từ khóa khác đi")


async def setup(bot):
    await bot.add_cog(wiki(bot))
