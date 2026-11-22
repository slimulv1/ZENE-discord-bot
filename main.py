"""Legacy entrypoint — kept only for rollback. Prefer ``python run.py``."""

import asyncio
import json
import os
import sys
from pathlib import Path

import discord
from colorama import Fore, Style
from discord.ext import commands
from tqdm import tqdm

tokens = json.loads(Path("zene/TOKEN.json").read_text(encoding="utf-8"))["DISCORD_TOKEN"]
TOKEN = tokens
intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix=["z/", "Z/", "h/", "H/"], intents=intents)


async def load_extensions() -> None:
    content = await asyncio.to_thread(Path("extensions.txt").read_text, encoding="utf-8")
    for extension in (line.strip() for line in content.splitlines() if line.strip()):
        try:
            await bot.load_extension(extension)
            print("Loading", extension, Fore.GREEN + "...Done" + Style.RESET_ALL)
        except Exception as exc:  # noqa: BLE001 - legacy loader reports every failure
            print(Fore.RED + f"Failed loading {extension}: {exc}" + Style.RESET_ALL)


@bot.event
async def on_ready() -> None:
    await bot.change_presence(activity=discord.Game(name="Black Myth: Wukong"))


async def main() -> None:
    await load_extensions()
    print(Fore.CYAN + "Booting up Zene..." + Style.RESET_ALL)
    for _ in tqdm(range(100)):
        await asyncio.sleep(0.01)
    print(Fore.GREEN + "---------DONE---------" + Style.RESET_ALL)
    await bot.start(TOKEN)


def restart_bot() -> None:
    os.execv(sys.executable, [sys.executable, *sys.argv])  # noqa: S606 - intentional exec


@bot.command(name="restart")
async def restart(ctx: commands.Context) -> None:
    if ctx.author.id == 262844868919951360:
        await ctx.send("🫡 わかりました、ご主人様。")
        restart_bot()
    else:
        await ctx.send("Unauthorized!!!")


asyncio.run(main())
