"""Legacy nhentai commands with blocking SDK calls moved off the event loop."""
import asyncio
import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


def _client():
    from hentai import Hentai, Utils, Sort, Format  # noqa: F401

    return Hentai, Utils, Sort, Format


class nhentai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nhentai")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def nhentai(self, ctx, *, arg: str):
        if not ctx.channel.is_nsfw():
            await ctx.send("Qua kênh NSFW mà xài")
            return
        try:
            Hentai, _, _, Format = await asyncio.to_thread(_client)

            def work():
                doujin = Hentai(arg)
                return doujin.title(Format.Pretty), doujin.url

            title, url = await asyncio.to_thread(work)
            await ctx.send(f"**{title}: ** {url}")
        except Exception as exc:
            log.warning("nhentai lookup failed: %s", exc)
            await ctx.send("Không tìm thấy mã này hoặc API đang nghỉ.")

    @commands.command(name="search")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def search(self, ctx, *, arg: str):
        if not ctx.channel.is_nsfw():
            await ctx.send("Qua kênh NSFW mà xài")
            return
        try:
            Hentai, Utils, Sort, Format = await asyncio.to_thread(_client)

            def work():
                return list(Utils.search_by_query(arg, sort=Sort.PopularWeek))[:5]

            results = await asyncio.to_thread(work)
        except Exception as exc:
            log.warning("nhentai search failed: %s", exc)
            await ctx.send("Không tìm thấy")
            return

        for index, doujin in enumerate(results, 1):
            embed = discord.Embed(
                title=f"{index}. {doujin.title(Format.Pretty)}",
                description=doujin.url,
                color=discord.Colour.teal(),
            )
            try:
                embed.set_image(url=doujin.image_urls[0])
            except (IndexError, TypeError):
                pass
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(nhentai(bot))
