"""Social-media link embed fixer cog (disabled by default)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Iterable
from io import BytesIO

import discord
from cachetools import TTLCache
from discord.ext import commands

from ..avwiki import looks_vietnamese, to_vietnamese
from ..embedfix.adapters import MetaAdapter, YtDlpAdapter
from ..embedfix.guards import canonicalize, is_asset_url, url_hash
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
from ..net import get_session

log = logging.getLogger(__name__)


def _compose_avatar_bytes(user_bytes: bytes, bot_bytes: bytes) -> bytes:
    """Composite the bot avatar over the user avatar at the status-dot corner.

    Discord's status dot is ~30% of the chat avatar diameter; the requested
    badge is 125% of that, i.e. 37.5% of the base. Everything runs in-memory.
    """
    from PIL import Image, ImageDraw

    size = 256
    badge_size = 96  # 37.5% of 256

    def circular(image: Image.Image, target: int) -> Image.Image:
        image = image.convert("RGBA").resize((target, target), Image.Resampling.LANCZOS)
        mask = Image.new("L", (target, target), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, target - 1, target - 1), fill=255)
        image.putalpha(mask)
        return image

    with Image.open(BytesIO(user_bytes)) as image:
        base = circular(image, size)
    with Image.open(BytesIO(bot_bytes)) as image:
        badge = circular(image, badge_size)

    border = 4
    ring = Image.new("RGBA", (badge_size + border * 2, badge_size + border * 2), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=(43, 45, 49, 255))
    ring.alpha_composite(badge, (border, border))

    margin = 4
    base.alpha_composite(ring, (size - ring.width - margin, size - ring.height - margin))
    out = BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


class EmbedFixCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        cfg = bot.config
        self.queue: asyncio.Queue[LinkContext] = asyncio.Queue(maxsize=cfg.media_queue_size)
        self.semaphore = asyncio.Semaphore(cfg.media_workers)
        self.cache: TTLCache = TTLCache(maxsize=512, ttl=max(1, cfg.media_cache_ttl))
        self.video_cache: TTLCache = TTLCache(maxsize=512, ttl=max(60, cfg.media_direct_video_ttl))
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 3.0, commands.BucketType.user)
        self._webhooks: dict[int, discord.Webhook] = {}
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

    def _embed_hints(self, message: discord.Message, raw: str) -> tuple[tuple[str, ...], str, str]:
        """Reuse media Discord already resolved in its native link embed."""
        urls: list[str] = []
        title = ""
        context = ""
        for embed in message.embeds:
            embed_url = str(getattr(embed, "url", "") or "")
            if embed_url and raw not in embed_url and embed_url not in raw:
                continue
            image = getattr(embed, "image", None)
            media_url = str(getattr(image, "url", "") or "") if image is not None else ""
            if media_url and is_asset_url(
                media_url, self.cfg.media_allowed_domains, self.cfg.media_proxy_hosts
            ):
                urls.append(media_url)
            if not title:
                title = str(getattr(embed, "title", "") or "")
            if not context:
                context = str(getattr(embed, "description", "") or "")
        return tuple(dict.fromkeys(urls)), title, context

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
            hints, hint_title, hint_context = self._embed_hints(message, raw)
            try:
                self.queue.put_nowait(
                    LinkContext(
                        message,
                        raw,
                        canonical,
                        mods,
                        lang,
                        media_hints=hints,
                        hint_title=hint_title,
                        hint_context=hint_context,
                    )
                )
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

        # Instagram: ifx often 500s on reel shortcodes while the generic meta
        # probe already has og:image. Run both at once and take the richer hit.
        if names == ("ifx", "meta") and {"ifx", "meta"} <= self.adapter_pool.keys():
            ifx, meta = await asyncio.gather(
                self.adapter_pool["ifx"].probe(
                    ctx.canonical,
                    allowed,
                    self.cfg.media_timeout,
                    proxy_hosts=proxies,
                    max_bytes=self.cfg.media_max_bytes,
                ),
                self.adapter_pool["meta"].probe(
                    ctx.canonical,
                    allowed,
                    self.cfg.media_timeout,
                    proxy_hosts=proxies,
                    max_bytes=self.cfg.media_max_bytes,
                ),
                return_exceptions=True,
            )
            ran = 2
            results = [item for item in (ifx, meta) if isinstance(item, ProbeResult)]
            best = (
                next((item for item in results if item.kind in {"video", "gallery"}), None)
                or next((item for item in results if item.kind == "image"), None)
                or next((item for item in results if item.kind == "link"), None)
            )
            self._record_probe(started, ran)
            return best

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
        # Native Discord embeds already contain the full carousel. Prefer them
        # over re-probing (ifx is often down) and never reuse a stale single
        # image from cache when fresh hints are available.
        result = None if ctx.media_hints else (self.video_cache.get(key) or self.cache.get(key))
        if result is None:
            if ctx.media_hints:
                kind = "gallery" if len(ctx.media_hints) > 1 else "image"
                result = ProbeResult(
                    kind,
                    ctx.hint_title,
                    "",
                    ctx.media_hints,
                    ctx.hint_context,
                    False,
                    ctx.canonical,
                )
                self.bot.stats["embedfix_native_hints"] += 1
            else:
                result = await self._probe(ctx)
            if result is None:
                await ctx.message.channel.send(content="Không lấy được media từ link này.")
                self.bot.stats["embedfix_no_media"] += 1
                return
            if result.kind in {"video", "gallery"}:
                self.video_cache[key] = result
            else:
                self.cache[key] = result

        if result.kind == "link":
            await ctx.message.channel.send(content=result.page_url)
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

        impersonated = False
        if self.cfg.media_mode == "impersonate":
            impersonated = await self._send_impersonated(ctx, view)
        if not impersonated:
            await ctx.message.channel.send(view=view)
        self.bot.stats["embedfix_ok"] += 1
        if result.kind in {"video", "gallery"}:
            self.bot.stats["embedfix_video_ok"] += 1

        if self.cfg.media_mode == "replace" or impersonated:
            await self._replace(ctx.message)

    def _nsfw_allowed(self, ctx: LinkContext, result: ProbeResult) -> bool:
        if not self.cfg.nsfw_enabled:
            return True
        sensitive = result.nsfw is True or (result.nsfw is None and self.cfg.media_strict_nsfw)
        return not sensitive or bool(ctx.message.channel.is_nsfw())

    async def _get_webhook(self, channel) -> discord.Webhook:
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached
        if self.cfg.media_webhook_url:
            webhook = discord.Webhook.from_url(self.cfg.media_webhook_url, client=self.bot)
        else:
            webhook = await channel.create_webhook(name="zene-embed")
        self._webhooks[channel.id] = webhook
        return webhook

    async def _avatar_bytes(self, url: str) -> bytes:
        session = await get_session()
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            return await response.read()

    async def _send_impersonated(self, ctx: LinkContext, view) -> bool:
        """Send as the author with the bot badge on their avatar, then remove theirs."""
        message = ctx.message
        author = message.author
        guild = message.guild
        can_create_webhook = (
            guild is None or message.channel.permissions_for(guild.me).manage_webhooks
        )
        temp_webhook: discord.Webhook | None = None

        try:
            composed: bytes | None = None
            if can_create_webhook and self.bot.user is not None:
                try:
                    user_bytes = await self._avatar_bytes(author.display_avatar.url)
                    bot_bytes = await self._avatar_bytes(self.bot.user.display_avatar.url)
                    composed = await asyncio.to_thread(_compose_avatar_bytes, user_bytes, bot_bytes)
                except Exception as exc:  # noqa: BLE001 - avatar is cosmetic
                    log.debug("không ghép được badge avatar: %s", exc)

            if composed is not None:
                # Webhook.send only accepts an avatar URL, so a temporary
                # webhook with the composed bytes is the per-message solution.
                temp_webhook = await message.channel.create_webhook(
                    name="zene-embed", avatar=composed
                )
                await temp_webhook.send(username=author.display_name, view=view, wait=True)
                self.bot.stats["embedfix_avatar_badge"] += 1
            else:
                webhook = await self._get_webhook(message.channel)
                await webhook.send(
                    username=author.display_name,
                    avatar_url=author.display_avatar.url,
                    view=view,
                    wait=True,
                )
            self.bot.stats["embedfix_impersonated"] += 1
            return True
        except (discord.HTTPException, discord.Forbidden, TypeError, ValueError) as exc:
            log.warning("impersonate thất bại, gửi thường: %s", exc)
            return False
        finally:
            if temp_webhook is not None:
                with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                    await temp_webhook.delete()

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
