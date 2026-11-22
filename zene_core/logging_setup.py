"""Structured, rotating, secret-redacting logging."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler

from .config import Config

_CONFIGURED_FLAG = "_zene_core_configured"


class SecretRedactingFilter(logging.Filter):
    """Best-effort scrubbing so a token can never leak into a log line."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s and len(s) >= 8)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            # Malformed args must never break logging itself.
            return True
        for secret in self._secrets:
            message = message.replace(secret, "***REDACTED***")
        record.msg = message
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line — friendly to Docker / log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(config: Config) -> None:
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return

    root.setLevel(getattr(logging, config.log_level, logging.INFO))
    formatter = JsonFormatter()
    redactor = SecretRedactingFilter((config.token,))

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    root.addHandler(stream_handler)

    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.log_dir / "zene.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
    except OSError as exc:
        # Read-only filesystem must not stop the bot from running.
        root.warning("Không thể tạo file log, dùng stdout: %s", exc)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    setattr(root, _CONFIGURED_FLAG, True)
    root.info("logging ready — %s", config.summary())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
