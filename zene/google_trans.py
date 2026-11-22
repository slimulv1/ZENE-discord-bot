import asyncio

from deep_translator import GoogleTranslator
from discord.ext import commands


class translate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def trans(self, ctx, *, arg):
        def work():
            return GoogleTranslator(source='auto', target='vi').translate(str(arg))

        try:
            await ctx.reply(await asyncio.to_thread(work))
        except Exception:
            await ctx.reply('http://translate.google.com/')


async def setup(bot):
    await bot.add_cog(translate(bot))
