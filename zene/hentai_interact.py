"""Legacy NSFW/image commands, migrated to non-blocking HTTP.

Public command names and replies are unchanged; only the transport changed:
``requests.get`` now runs in a worker thread behind the shared circuit breaker.
"""
import random
from typing import Optional

from discord.ext import commands

from zene_core.net import fetch_json

nsfw_direct = 'Qua kênh NSFW mà xài'
warning = 'Xem hentai nhiều có hại cho sức khỏe. Chọn số dưới 10 thôi'
degraded = 'API đang nghỉ ngơi, thử lại sau nhé.'

LEWD_ENDPOINTS = [
    'https://api.waifu.pics/nsfw/waifu',
    'http://api.nekos.fun:8080/api/lewd',
    'http://api.nekos.fun:8080/api/hentai',
    'https://api.waifu.pics/nsfw/neko',
    'https://neko-love.xyz/api/v1/nekolewd',
]
NEKO_ENDPOINTS = [
    'https://api.waifu.pics/nsfw/neko',
    'https://neko-love.xyz/api/v1/nekolewd',
]


async def _image_url(url: str) -> Optional[str]:
    payload = await fetch_json(url, name="hentai-api")
    if not isinstance(payload, dict):
        return None
    # Different APIs use either "url" or "image" for the same field.
    value = payload.get("url") or payload.get("image")
    return str(value) if value else None


class hentai_random(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _allowed(ctx, number: int) -> bool:
        if number <= 0:
            return False
        if number > 10:
            return False
        return ctx.channel.is_nsfw()

    @commands.command()
    async def hen(self, ctx, number: int):
        if number > 10:
            await ctx.send(warning)
            return
        if number <= 0 or not ctx.channel.is_nsfw():
            await ctx.send(nsfw_direct)
            return
        for _ in range(number):
            image = await _image_url(random.choice(LEWD_ENDPOINTS))
            await ctx.send(image if image else degraded)

    @commands.command()
    async def hentai(self, ctx, number: int):
        # Safety parity with `hen`: never leak NSFW content outside NSFW channels.
        if number > 10:
            await ctx.send(warning)
            return
        if number <= 0 or not ctx.channel.is_nsfw():
            await ctx.send(nsfw_direct)
            return
        for _ in range(number):
            image = await _image_url(random.choice(LEWD_ENDPOINTS))
            await ctx.send(image if image else degraded)

    @commands.command()
    async def hentrap(self, ctx, number: int):
        if number > 10:
            await ctx.send(warning)
            return
        if number <= 0 or not ctx.channel.is_nsfw():
            await ctx.send(nsfw_direct)
            return
        for _ in range(number):
            image = await _image_url('https://api.waifu.pics/nsfw/trap')
            await ctx.send(image if image else degraded)

    @commands.command()
    async def henneko(self, ctx, number: int):
        if number > 10:
            await ctx.send(warning)
            return
        if number <= 0 or not ctx.channel.is_nsfw():
            await ctx.send(nsfw_direct)
            return
        for _ in range(number):
            image = await _image_url(random.choice(NEKO_ENDPOINTS))
            await ctx.send(image if image else degraded)

    @commands.command()
    async def henbj(self, ctx):
        if not ctx.channel.is_nsfw():
            await ctx.send(nsfw_direct)
            return
        image = await _image_url('https://api.waifu.pics/nsfw/blowjob')
        await ctx.send(image if image else degraded)

    @commands.command()
    async def mlem(self, ctx):
        image = await _image_url('http://api.nekos.fun:8080/api/lick')
        await ctx.send(image if image else degraded)

    @commands.command()
    async def slap(self, ctx, *, god=None):
        owner_id = 262844868919951360
        if getattr(god, 'id', None) != owner_id:
            image = await _image_url('http://api.nekos.fun:8080/api/slap')
            await ctx.send(image if image else degraded)
        else:
            await ctx.send('<@262844868919951360> Có đứa định slap Onii-sama. Để em xiên nó :angry:')

    @commands.command()
    async def waifu(self, ctx):
        image = await _image_url('https://api.waifu.pics/sfw/waifu')
        await ctx.send(image if image else degraded)


async def setup(bot):
    await bot.add_cog(hentai_random(bot))
