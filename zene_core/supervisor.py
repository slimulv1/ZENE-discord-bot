"""Process supervisor: supervised restarts, backoff, and a dependency-free health endpoint."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Callable, Optional

import discord

from .bot import ZeneBot
from .config import Config
from .state import RuntimeState

log = logging.getLogger(__name__)

BotFactory = Callable[[Config, RuntimeState], ZeneBot]


class Supervisor:
    def __init__(self, config: Config, state: RuntimeState, factory: BotFactory) -> None:
        self.config = config
        self.state = state
        self.factory = factory
        self.started_at = time.monotonic()
        self._bot: Optional[ZeneBot] = None
        self._health_server: Optional[asyncio.AbstractServer] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    # ------------------------------------------------------------- lifecycle --
    async def run(self) -> None:
        self._shutdown_event = asyncio.Event()
        await self._start_health_server()
        try:
            await self._supervise()
        finally:
            await self._stop_health_server()

    async def _supervise(self) -> None:
        failures = 0
        first_boot = True
        while True:
            # A signal may arrive while we are backing off; never boot a new
            # client after shutdown was requested.
            if self.state.shutdown_requested:
                log.info("shutdown requested trước khi boot — kết thúc supervisor")
                return
            if not first_boot:
                # Count every respawn (crash or operator request), not just /restart.
                self.state.restarts += 1
            first_boot = False
            bot = self.factory(self.config, self.state)
            self._bot = bot
            counted = False
            try:
                log.info("boot attempt %d (restarts=%d)", failures + 1, self.state.restarts)
                # ``async with`` guarantees close() on every exit path.
                # Only the login phase is time-boxed: ``connect()`` is the
                # long-lived gateway session and must not be cancelled.
                async with bot:
                    await asyncio.wait_for(
                        bot.login(self.config.token), timeout=self.config.boot_timeout
                    )
                    await bot.connect()
            except asyncio.CancelledError:
                raise
            except discord.LoginFailure:
                log.critical("Token không hợp lệ — dừng, không retry vô hạn.")
                return
            except discord.PrivilegedIntentsRequired:
                log.critical(
                    "Thiếu privileged intents. Bật Message Content Intent trong Discord Developer Portal."
                )
                return
            except asyncio.TimeoutError:
                failures += 1
                counted = True
                log.error("Login quá thời gian (%ss)", self.config.boot_timeout)
            except Exception as exc:  # noqa: BLE001 - supervisor boundary
                failures += 1
                counted = True
                log.error("bot crashed: %s: %s", type(exc).__name__, exc)
            finally:
                self._bot = None

            # A crash after a long healthy run is an isolated incident, not a
            # crash-loop: decay the failure counter instead of accumulating it.
            if (time.monotonic() - bot.started_at) >= self.config.stable_seconds:
                failures = 0

            if self.state.shutdown_requested:
                log.info("shutdown requested — kết thúc supervisor")
                return

            if self.state.restart_requested:
                self.state.restart_requested = False
                failures = 0
                log.info("restart có chủ đích — khởi tạo lại bot trong cùng process")
                continue

            if not counted:
                # connect() returning without an explicit stop is abnormal —
                # counting it prevents a zero-delay respawn loop.
                failures += 1
                log.error("bot.connect() trả về bất thường — tính là crash")

            if failures > self.config.max_restarts:
                log.critical("vượt quá %d lần restart — dừng để tránh crash-loop", self.config.max_restarts)
                return

            delay = min(
                self.config.backoff_cap,
                self.config.backoff_base * (2 ** max(0, failures - 1)),
            )
            delay *= 1.0 + random.uniform(-0.2, 0.2)
            log.warning("sẽ khởi động lại sau %.1fs (failures=%d)", max(0.0, delay), failures)
            if self._shutdown_event is not None:
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=max(0.0, delay)
                    )
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(max(0.0, delay))

    def request_shutdown(self) -> None:
        """Called from a signal handler running inside the event loop."""
        self.state.shutdown_requested = True
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        bot = self._bot
        if bot is not None and not getattr(bot, "_closing", False) and not bot.is_closed():
            asyncio.get_running_loop().create_task(bot.close())

    # --------------------------------------------------------------- health --
    async def _start_health_server(self) -> None:
        if self.config.health_port <= 0:
            log.info("health server bị tắt (HEALTH_PORT<=0)")
            return
        try:
            self._health_server = await asyncio.start_server(
                self._handle_health, self.config.health_host, self.config.health_port
            )
            log.info(
                "health endpoint: http://%s:%d/health",
                self.config.health_host,
                self.config.health_port,
            )
        except OSError as exc:
            log.warning("không mở được health server: %s", exc)

    async def _stop_health_server(self) -> None:
        if self._health_server is not None:
            self._health_server.close()
            await self._health_server.wait_closed()
            self._health_server = None

    async def _handle_health(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = (
                await asyncio.wait_for(reader.readline(), timeout=2.0)
            ).decode("utf-8", "replace").strip()
            if not request_line.upper().startswith("GET /health"):
                writer.write(
                    b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
                await writer.drain()
                return
            bot = self._bot
            ready = bool(bot is not None and bot.is_ready())
            degraded = bool(
                bot is not None and (bot.failed_extensions or bot.stats["missing_assets"])
            )
            healthy = ready and not degraded and not self.state.shutdown_requested
            payload = {
                "status": "ok" if healthy else "degraded",
                "ready": ready,
                "uptime_seconds": round(time.monotonic() - self.started_at, 1),
                "restarts": self.state.restarts,
                "failed_extensions": sorted(bot.failed_extensions) if bot else [],
                "stats": dict(bot.stats) if bot else {},
                "asset_commands": bot.assets.command_count if bot else 0,
            }
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            status_line = "200 OK" if healthy else "503 Service Unavailable"
            header = (
                f"HTTP/1.1 {status_line}\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(raw)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(header + raw)
            await writer.drain()
        except (asyncio.TimeoutError, OSError, ConnectionError):
            pass
        finally:
            writer.close()
