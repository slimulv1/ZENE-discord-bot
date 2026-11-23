"""Check code/data against documented Discord limits."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import discord

from zene_core.bot import ZeneBot
from zene_core.cogs.amlich import _render as render_amlich
from zene_core.cogs.giaxang import _render as render_giaxang
from zene_core.cogs.ops import OpsCog
from zene_core.config import Config
from zene_core.state import RuntimeState

ROOT = Path.cwd()
errors: list[str] = []
warnings: list[str] = []


def check_embed(name: str, embed: discord.Embed) -> None:
    data = embed.to_dict()
    if len(embed) > 6000:
        errors.append(f"{name}: embed total {len(embed)} > 6000")
    fields = data.get("fields", [])
    if len(fields) > 25:
        errors.append(f"{name}: {len(fields)} fields > 25")
    if len(data.get("description", "")) > 4096:
        errors.append(f"{name}: description > 4096")
    for field in fields:
        if len(field["name"]) > 256:
            errors.append(f"{name}: field name > 256")
        if len(field["value"]) > 1024:
            errors.append(f"{name}: field value > 1024")
    print(f"  embed {name}: {len(embed)} chars, {len(fields)} fields")


def main() -> None:
    data = json.loads((ROOT / "zene/data/memes.json").read_text(encoding="utf-8"))
    for section in ("text_triggers", "command_texts"):
        longest_key, longest = max(
            ((k, len(v)) for k, v in data[section].items()), key=lambda x: x[1]
        )
        print(f"{section}: max length {longest} ({longest_key[:30]!r})")
        if longest > 2000:
            errors.append(f"{section}: message {longest_key!r} > 2000 chars")
    for section in ("anxin_stories",):
        longest = max(len(v) for v in data[section])
        print(f"{section}: max length {longest}")
        if longest > 2000:
            errors.append(f"{section}: story > 2000 chars")
    for key, stories in data["choice_triggers"].items():
        longest = max(len(v) for v in stories)
        print(f"choice {key!r}: max length {longest}")
        if longest > 2000:
            errors.append(f"choice {key!r}: story > 2000 chars")

    max_size = 0
    max_rel = ""
    for rel in data["assets"].values():
        size = (ROOT / rel).stat().st_size
        if size > max_size:
            max_size, max_rel = size, rel
        if size > 8 * 1024 * 1024:
            errors.append(f"asset {rel} > 8MB")
    print(f"largest asset: {max_size / 1024 / 1024:.2f} MB ({max_rel})")

    bot = ZeneBot(Config(token="x" * 40), RuntimeState())

    async def run() -> None:
        for ext in bot.config.required_extensions + bot.config.optional_extensions:
            await bot.load_extension(ext)
        for cmd in bot.tree.get_commands():
            payload = cmd.to_dict(bot.tree)
            name = payload["name"]
            if not re.fullmatch(r"[\w-]{1,32}", name):
                errors.append(f"slash name invalid: {name}")
            if len(payload["description"]) > 100 or not payload["description"]:
                errors.append(f"slash description invalid: {name}")
            options = payload.get("options", [])
            if len(options) > 25:
                errors.append(f"slash {name}: >25 options")
            for opt in options:
                if len(opt["name"]) > 32 or len(opt.get("description", "")) > 100:
                    errors.append(f"slash {name}: option length invalid")
            print(f"  /{name}: ok")

        # Worst-case-ish embeds from real helpers.
        today = __import__("datetime").date.today()
        check_embed("amlich", render_amlich(today))
        rows = [[{"title": f"X{i}", "zone1_price": 1, "zone2_price": 2} for i in range(7)]]
        check_embed("giaxang", render_giaxang(today, rows))

        sent = {}

        async def safe_send(target, **kwargs):
            sent["embed"] = kwargs.get("embed")

        fake_bot = SimpleNamespace(
            started_at=time.monotonic() - 100000,
            latency=0.05,
            is_ready=lambda: True,
            failed_extensions={"a": "x", "b": "y"},
            stats={"trigger_hits": 1, "missing_assets": 1},
            state=SimpleNamespace(restarts=3),
            guilds=[1, 2],
            triggers=[1] * 18,
            assets=SimpleNamespace(command_count=94),
            safe_send=safe_send,
        )
        cog = OpsCog(fake_bot)

        class Ctx:
            async def defer(self):
                return None

        await cog.health.callback(cog, Ctx())
        check_embed("health", sent["embed"])

    asyncio.run(run())

    print("errors:", len(errors))
    for item in errors:
        print("  ERROR", item)
    print("warnings:", len(warnings))
    for item in warnings:
        print("  WARN", item)


if __name__ == "__main__":
    main()
