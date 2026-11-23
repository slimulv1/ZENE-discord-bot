"""Social-media link embed fixer cog (disabled by default)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Iterable

import discord
from cachetools import TTLCache
from discord.ext import commands

from ..avwiki import looks_vietnamese, to_vietnamese
from ..embedfix.adapters import MetaAdapter, YtDlpAdapter
from ..embedfix.guards import canonicalize, url_hash
from ..embedfix.models import LinkContext, ProbeResult
from ..embedfix.modifiers import LINK_RE, parse_modifiers
from ..embedfix.proxy_adapters import (
    FacebedAdapter,
    FxEmbedAdapter,
    IfxAdapter,
    TiktokProxyAdapter,
    XDirectAdapter,
)
from ..embedfix.router import route_for
from ..embedfix.views import build_view

log = logging.getLogger(__name__)


class EmbedFixCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        cfg = bot.config
        self.queue: asyncio.Queue[LinkContext] = asyncio.Queue(maxsize=cfg.media_queue_size)
        self.semaphore = asyncio.Semaphore(cfg.media_workers)
        self.cache: TTLCache = TTLCache(maxsize=512, ttl=max(1, cfg.media_cache_ttl))
        self.video_cache: TTLCache = TTLCache(maxsize=512, ttl=max(60, cfg.media_direct_video_ttl))
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 3.0, commands.BucketType.user)
        self.adapter_pool: dict[str, object] = {"meta": MetaAdapter()}
        if cfg.media_use_proxies:
            self.adapter_pool.update(
                {
                    "fxtwitter": FxEmbedAdapter(),
                    "x-direct": XDirectAdapter(),
                    "ifx": IfxAdapter(),
                    "tnktok": TiktokProxyAdapter(),
                    "facebed": FacebedAdapter(),
                }
            )
        if cfg.media_use_ytdlp:
            self.adapter_pool["ytdlp"] = YtDlpAdapter()
        self._task: asyncio.Task | None = None

    @property
    def cfg(self):
        return self.bot.config

    async def cog_load(self) -> None:
        if not self.cfg.media_links_enabled:
            log.info("embedfix tắt (ZENE_MEDIA_LINKS_ENABLED=false)")
            return
        if not self.cfg.media_allowed_domains:
            log.warning(
                "embedfix bật nhưng ZENE_MEDIA_ALLOWED_DOMAINS trống — không xử lý link nào"
            )
            return
        self._task = asyncio.create_task(self._worker())
        log.info(
            "embedfix ready: %d adapter, %d worker", len(self.adapter_pool), self.cfg.media_workers
        )

    async def cog_unload(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self.cfg.media_links_enabled or not self.cfg.media_allowed_domains:
            return
        if message.author.bot or message.guild is None:
            return
        if self.cooldown.update_rate_limit(message) is not None:
            return

        raw_links = [match.group(0) for match in LINK_RE.finditer(message.content or "")]
        if not raw_links:
            # Links that arrive only as an auto-embed (no visible content).
            raw_links = [str(embed.url) for embed in message.embeds if getattr(embed, "url", None)]
        if not raw_links or len(raw_links) > self.cfg.media_max_links:
            return

        content = message.content or ""
        for raw in raw_links:
            position = content.find(raw)
            _, mods, lang = parse_modifiers(content[:position] if position >= 0 else "")
            try:
                canonical = await canonicalize(
                    raw,
                    self.cfg.media_allowed_domains,
                    timeout=self.cfg.media_timeout,
                )
            except ValueError:
                continue
            try:
                self.queue.put_nowait(LinkContext(message, raw, canonical, mods, lang))
            except asyncio.QueueFull:
                self.bot.stats["embedfix_dropped"] += 1
                return
            self.bot.stats["embedfix_seen"] += 1

    async def _worker(self) -> None:
        while True:
            ctx = await self.queue.get()
            try:
                async with self.semaphore:
                    await self._process(ctx)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - worker boundary
                log.warning("embedfix failed: %s", exc)
                self.bot.stats["embedfix_error"] += 1
            finally:
                self.queue.task_done()

    async def _probe(self, ctx: LinkContext) -> ProbeResult | None:
        allowed: Iterable[str] = self.cfg.media_allowed_domains
        proxies: Iterable[str] = self.cfg.media_proxy_hosts
        names = route_for(ctx.canonical, self.cfg.media_use_proxies)
        if "ytdlp" in self.adapter_pool:
            names = (*names, "ytdlp")
        best: ProbeResult | None = None
        started = time.monotonic()
        ran = 0
        for name in names:
            adapter = self.adapter_pool.get(name)
            if adapter is None:
                continue
            ran += 1
            result = await adapter.probe(
                ctx.canonical,
                allowed,
                self.cfg.media_timeout,
                proxy_hosts=proxies,
                max_bytes=self.cfg.media_max_bytes,
            )
            if result.kind in {"video", "gallery"}:
                self._record_probe(started, ran)
                return result
            if (result.kind == "image" and (best is None or best.kind in {"none", "link"})) or (
                result.kind == "link" and best is None
            ):
                best = result
        self._record_probe(started, ran)
        return best

    def _record_probe(self, started: float, adapters: int) -> None:
        elapsed = max(0.0, time.monotonic() - started)
        self.bot.stats["embedfix_probe_ms"] += int(elapsed * 1000)
        self.bot.stats["embedfix_probe_count"] += 1
        self.bot.stats["embedfix_adapters_run"] += adapters

    async def _process(self, ctx: LinkContext) -> None:
        key = url_hash(ctx.canonical)
        result = self.video_cache.get(key) or self.cache.get(key)
        if result is None:
            result = await self._probe(ctx)
            if result is None:
                await ctx.message.reply(
                    content="Không lấy được media từ link này.", mention_author=False
                )
                self.bot.stats["embedfix_no_media"] += 1
                return
            if result.kind in {"video", "gallery"}:
                self.video_cache[key] = result
            else:
                self.cache[key] = result

        if result.kind == "link":
            await ctx.message.reply(content=result.page_url, mention_author=False)
            self.bot.stats["embedfix_link_embed"] += 1
            return

        if not self._nsfw_allowed(ctx, result):
            return

        spoiler = "spoiler" in ctx.modifiers
        hide_quote = "hide_quote" in ctx.modifiers
        title = result.title
        body = result.context
        if self.cfg.media_auto_translate or "translate" in ctx.modifiers or ctx.lang:
            target = ctx.lang or self.cfg.media_lang
            combined = "\n".join(part for part in (title, body) if part)
            if combined and not (target == "vi" and looks_vietnamese(combined)):
                # One API call for both fields instead of two.
                translated = await to_vietnamese(combined)
                if translated != combined:
                    parts = translated.split("\n", 1)
                    if title:
                        title = parts[0]
                    if body:
                        body = parts[1] if len(parts) > 1 else ""
            log.debug("embedfix translate target=%s", target)

        view = build_view(
            result,
            spoiler=spoiler,
            hide_quote=hide_quote,
            title=title,
            context=body,
        )
        if self.cfg.media_suppress:
            await self._suppress(ctx.message)
        await ctx.message.reply(view=view, mention_author=False)
        self.bot.stats["embedfix_ok"] += 1
        if result.kind in {"video", "gallery"}:
            self.bot.stats["embedfix_video_ok"] += 1

        if self.cfg.media_mode == "replace":
            await self._replace(ctx.message)

    def _nsfw_allowed(self, ctx: LinkContext, result: ProbeResult) -> bool:
        sensitive = result.nsfw is True or (result.nsfw is None and self.cfg.media_strict_nsfw)
        return not sensitive or bool(ctx.message.channel.is_nsfw())

    async def _suppress(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or not message.channel.permissions_for(guild.me).manage_messages:
            return
        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await message.edit(suppress=True)

    async def _replace(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or not message.channel.permissions_for(guild.me).manage_messages:
            return
        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await message.delete()


async def setup(bot) -> None:
    await bot.add_cog(EmbedFixCog(bot))
