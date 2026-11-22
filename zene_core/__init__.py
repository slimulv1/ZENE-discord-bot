"""Zene Core — production-grade runtime layer for the Zene Discord bot.

The legacy ``zene`` package is intentionally left untouched so this layer can be
adopted (or rolled back) without destroying the original meme content.
"""

__all__ = [
    "assets",
    "bot",
    "config",
    "content",
    "logging_setup",
    "resilience",
    "supervisor",
    "triggers",
]
