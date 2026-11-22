#!/usr/bin/env python3
"""Production entrypoint:  python run.py   (legacy main.py is kept for rollback)."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys

from dotenv import load_dotenv

from zene_core.bot import build_bot
from zene_core.config import Config, ConfigurationError
from zene_core.logging_setup import setup_logging
from zene_core.state import RuntimeState
from zene_core.supervisor import Supervisor


async def _run(config: Config) -> None:
    state = RuntimeState()
    supervisor = Supervisor(config, state, build_bot)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows / restricted environments: KeyboardInterrupt still works.
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, supervisor.request_shutdown)

    await supervisor.run()


def main() -> int:
    load_dotenv()  # local .env support; harmless when env vars are already set
    try:
        config = Config.from_env()
    except ConfigurationError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2

    setup_logging(config)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
