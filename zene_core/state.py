"""Process-level state shared between the supervisor and the bot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeState:
    restart_requested: bool = False
    shutdown_requested: bool = False
    restarts: int = 0
