"""The bot subclass: boot, load, observe, degrade, shut down cleanly."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .assets import AssetRegistry
from .config import Config
from .content import build_registry
from .state import RuntimeState
from .triggers import TriggerRegistry

log = logging.getLogger(__name__)


class ZeneBot(commands.Bot):
    def __init__(self, config: Config, state: RuntimeState) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required for prefix commands in discord.py 2.x
        intents.members = config.members_intent  # privileged — off by default

        super().__init__(
            command_prefix=config.command_prefixes,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            owner_ids=config.owner_ids,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=True
            ),
        )
        self.config = config
        self.state = state
        self.assets = AssetRegistry(config.root, config.data_dir, config.max_asset_bytes)
        self.triggers: TriggerRegistry = build_registry()
        self.failed_extensions: dict[str, str] = {}
        self.stats: Counter[str] = Counter()
        self.started_at = time.monotonic()
        self.ready_once = False
        self._send_semaphore = asyncio.Semaphore(8)
        self._closing = False

    # ---------------------------------------------------------------- boot --
    async def setup_hook(self) -> None:
        await super().setup_hook()
        await asyncio.to_thread(self.assets.load)

        for extension in self.config.required_extensions:
            await self._load_extension(extension, required=True)
        for extension in self.config.optional_extensions:
            await self._load_extension(extension, required=False)

        self.tree.on_error = self._on_tree_error
        try:
            synced = await self.tree.sync()
            log.info("slash commands synced: %d", len(synced))
        except Exception as exc:  # noqa: BLE001 - slash sync must not block prefix bot
            log.warning("slash sync failed: %s", exc)

    async def _load_extension(self, extension: str, *, required: bool) -> None:
        if extension in self.config.disabled_extensions:
            log.info("extension bị tắt bởi cấu hình: %s", extension)
            return
        try:
            await self.load_extension(extension)
            log.info("extension OK: %s", extension)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad cog must not kill the bot
            self.failed_extensions[extension] = f"{type(exc).__name__}: {exc}"
            level = log.error if required else log.warning
            level("extension thất bại %s: %s", extension, exc)

    async def reload_extension_safely(self, extension: str) -> tuple[bool, str]:
        try:
            await self.reload_extension(extension)
            self.failed_extensions.pop(extension, None)
            return True, f"Đã reload {extension}"
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator
            self.failed_extensions[extension] = f"{type(exc).__name__}: {exc}"
            return False, f"Reload {extension} thất bại: {exc}"

    # --------------------------------------------------------------- events --
    async def on_ready(self) -> None:
        # discord.py calls on_ready again after a failed RESUME (verified in docs).
        self.stats["ready_events"] += 1
        if not self.ready_once:
            self.ready_once = True
            log.info("READY as %s | guilds=%d", self.user, len(self.guilds))
            try:
                await self.change_presence(
                    activity=discord.Game(name=self.config.presence_name)
                )
            except discord.HTTPException as exc:
                log.warning("Không đổi được presence: %s", exc)

    async def on_connect(self) -> None:
        self.stats["connects"] += 1
        log.info("connected to Discord gateway")

    async def on_disconnect(self) -> None:
        self.stats["disconnects"] += 1
        log.warning("disconnected — discord.py sẽ tự reconnect")

    async def on_resumed(self) -> None:
        self.stats["resumes"] += 1
        log.info("gateway session resumed")

    async def on_command_error(self, context: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandOnCooldown):
            await self.safe_send(
                context, f"Chill đã bạn ơi... thử lại sau {error.retry_after:.1f}s."
            )
            return
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await self.safe_send(context, f"Sai cú pháp: {error}")
            return
        if isinstance(error, commands.CheckFailure):
            await self.safe_send(context, "Bạn không có quyền dùng lệnh này.")
            return
        if isinstance(error, commands.NoPrivateMessage):
            await self.safe_send(context, "Lệnh này chỉ dùng trong server.")
            return
        log.error("command error", exc_info=error)
        await self.safe_send(context, "Lỗi nội bộ, đã ghi log. Thử lại sau nhé.")

    async def _on_tree_error(
        self,
        interaction: discord.Interaction,
        command,
        error: Exception,
    ) -> None:
        """Slash-command errors need their own boundary (prefix uses on_command_error)."""
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"Chill đã bạn ơi... thử lại sau {error.retry_after:.1f}s."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Bạn không có quyền dùng lệnh này."
        else:
            log.error("slash command error: %s", getattr(command, "name", "?"), exc_info=error)
            message = "Lỗi nội bộ, đã ghi log. Thử lại sau nhé."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    # --------------------------------------------------------------- helpers --
    async def safe_send(self, target, content: Optional[str] = None, **kwargs):
        """Send without ever letting a Discord HTTP error escape into an event."""
        try:
            async with self._send_semaphore:
                return await target.send(content=content, **kwargs)
        except discord.Forbidden:
            log.warning("Không gửi được tới kênh %s (thiếu quyền)", getattr(target, "channel", target))
        except discord.HTTPException as exc:
            log.warning("HTTP error khi gửi tin nhắn: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - last-resort event boundary
            log.error("lỗi gửi không xác định: %s", exc)
        return None

    async def send_asset(self, target, relative: str, filename: Optional[str] = None):
        file = await self.assets.discord_file(relative, filename)
        if file is None:
            self.stats["missing_assets"] += 1
            return await self.safe_send(target, "Asset tạm thời không khả dụng.")
        return await self.safe_send(target, file=file)

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        log.info("đang đóng bot gracefully...")
        from .net import close_session

        await close_session()
        await super().close()


def build_bot(config: Config, state: RuntimeState) -> ZeneBot:
    return ZeneBot(config, state)
