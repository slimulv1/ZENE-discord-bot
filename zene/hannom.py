import json

from discord.ext import commands

from zene_core.net import fetch_text

URL = "https://hvdic.thivien.net/transcript-query.json.php"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}


class han2viet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def han(self, ctx, *, arg):
        payload = f"mode=trans&lang=3&input={arg}"
        raw = await fetch_text(
            URL,
            name="hvdic",
            method="POST",
            headers=HEADERS,
            data=payload.encode(),
        )
        if raw is None:
            await ctx.reply("Dịch Hán Việt tạm thời không khả dụng.")
            return

        try:
            result = json.loads(raw)["result"]
        except (ValueError, KeyError, TypeError):
            await ctx.reply("Không hiểu được phản hồi từ hvdic.")
            return

        lines = []
        for item in result:
            text = " ".join(item.get("o", []))
            if text:
                lines.append(text)

        reply = "\n".join(lines)
        await ctx.reply(f"{reply}\nhttps://hvdic.thivien.net/whv/{arg}")


async def setup(bot):
    await bot.add_cog(han2viet(bot))
