#!/usr/bin/env python3
"""Production entrypoint:  python run.py   (legacy main.py is kept for rollback)."""
from __future__ import annotations

import asyncio
import signal
import sys

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
        try:
            loop.add_signal_handler(sig, supervisor.request_shutdown)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows / restricted environments: KeyboardInterrupt still works.
            pass

    await supervisor.run()


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigurationError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 2

    setup_logging(config)
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
