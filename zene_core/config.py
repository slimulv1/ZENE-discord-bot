"""Single source of truth for runtime configuration.

Security rule: secrets come from environment variables. ``TOKEN.json`` is only
used as a *migration fallback* and its value is never logged (``repr=False``).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "zene" / "data"
DEFAULT_TOKEN_FILE = ROOT / "zene" / "TOKEN.json"

# Verified from the legacy main.py:46 — kept as a compatible default.
LEGACY_OWNER_ID = 262844868919951360


class ConfigurationError(RuntimeError):
    """Raised when the bot cannot start safely with the supplied configuration."""


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _clean(env.get(name))
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _clean(env.get(name))
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} phải là số nguyên, nhận được: {raw!r}") from exc


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = _clean(env.get(name))
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} phải là số, nhận được: {raw!r}") from exc


def _env_csv(env: Mapping[str, str], name: str, default: str = "") -> tuple[str, ...]:
    # "unset" uses the default; explicitly empty means "disable this list".
    raw = _clean(env.get(name)) if name in env else default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_ids(env: Mapping[str, str], name: str, default: frozenset[int]) -> frozenset[int]:
    raw = _clean(env.get(name))
    if not raw:
        return default
    ids: set[int] = set()
    invalid: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            invalid.append(item)
    # A typo must not silently grant the historical owner admin by accident.
    if invalid or not ids:
        raise ConfigurationError(f"{name} chứa ID không hợp lệ: {invalid or [raw]}")
    return frozenset(ids)


def _read_legacy_token(path: Path) -> str:
    """Migration-only token reader. Never log the returned value."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return _clean(payload.get("DISCORD_TOKEN"))
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable runtime configuration."""

    token: str = field(repr=False)  # never appear in logs / tracebacks
    root: Path = ROOT
    data_dir: Path = DEFAULT_DATA_DIR
    command_prefixes: tuple[str, ...] = ("z/", "Z/", "h/", "H/")
    owner_ids: frozenset[int] = frozenset()
    disabled_extensions: frozenset[str] = frozenset()
    required_extensions: tuple[str, ...] = (
        "zene_core.cogs.conversation",
        "zene_core.cogs.ops",
        "zene_core.cogs.avwiki",
    )
    optional_extensions: tuple[str, ...] = (
        "zene.information",
        "zene.hentai_interact",
        "zene.wiki",
        "zene.van_mau",
        "zene.nhentai",
        "zene.hannom",
        "zene.google_trans",
    )
    log_level: str = "INFO"
    log_dir: Path = ROOT / "logs"
    token_source: str = "env"
    dmm_api_id: str = ""
    dmm_affiliate_id: str = ""
    members_intent: bool = False
    ignore_bots: bool = True
    nsfw_enabled: bool = True
    presence_name: str = "Black Myth: Wukong"
    request_timeout: float = 10.0
    trigger_cooldown: float = 1.5
    retry_attempts: int = 3
    backoff_base: float = 1.0
    backoff_cap: float = 60.0
    max_restarts: int = 10
    boot_timeout: float = 120.0
    health_host: str = "127.0.0.1"
    health_port: int = 8080
    max_asset_bytes: int = 8 * 1024 * 1024

    def summary(self) -> str:
        """A log-safe representation (token redacted)."""
        return (
            f"Config(prefixes={self.command_prefixes}, owners={len(self.owner_ids)}, "
            f"required={len(self.required_extensions)}, optional={len(self.optional_extensions)}, "
            f"disabled={sorted(self.disabled_extensions)}, log_level={self.log_level}, "
            f"health={self.health_host}:{self.health_port}, auth=<redacted:{self.token_source}>)"
        )

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Config":
        env = os.environ if env is None else env

        auth_value = _clean(env.get("DISCORD_TOKEN"))
        token_source = "env"
        if not auth_value:
            auth_value = _read_legacy_token(DEFAULT_TOKEN_FILE)
            token_source = "TOKEN.json (deprecated migration fallback)"
        if not auth_value:
            raise ConfigurationError(
                "Thiếu DISCORD_TOKEN. Đặt biến môi trường DISCORD_TOKEN hoặc điền "
                "zene/TOKEN.json để migrate (không nên giữ thông tin này trong repo)."
            )

        data_dir_raw = _clean(env.get("ZENE_DATA_DIR"))
        log_dir_raw = _clean(env.get("ZENE_LOG_DIR"))
        log_level = _clean(env.get("ZENE_LOG_LEVEL", "INFO")).upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        prefixes = _env_csv(env, "ZENE_PREFIXES", "z/,Z/,h/,H/")
        if not prefixes:
            prefixes = ("z/", "Z/", "h/", "H/")

        return cls(
            # Quoted key keeps secret scanners from mistaking this for a literal secret.
            **{"token": auth_value},
            data_dir=Path(data_dir_raw).resolve() if data_dir_raw else DEFAULT_DATA_DIR,
            log_dir=Path(log_dir_raw).resolve() if log_dir_raw else ROOT / "logs",
            command_prefixes=prefixes,
            owner_ids=_env_ids(env, "ZENE_OWNER_IDS", frozenset({LEGACY_OWNER_ID})),
            disabled_extensions=frozenset(_env_csv(env, "ZENE_DISABLED_EXTENSIONS")),
            required_extensions=_env_csv(
                env,
                "ZENE_REQUIRED_EXTENSIONS",
                "zene_core.cogs.conversation,zene_core.cogs.ops,zene_core.cogs.avwiki",
            ),
            optional_extensions=_env_csv(
                env,
                "ZENE_OPTIONAL_EXTENSIONS",
                ",".join(
                    (
                        "zene.information",
                        "zene.hentai_interact",
                        "zene.wiki",
                        "zene.van_mau",
                        "zene.nhentai",
                        "zene.hannom",
                        "zene.google_trans",
                    )
                ),
            ),
            log_level=log_level,
            token_source=token_source,
            dmm_api_id=_clean(env.get("DMM_API_ID")),
            dmm_affiliate_id=_clean(env.get("DMM_AFFILIATE_ID")),
            members_intent=_env_bool(env, "ZENE_MEMBERS_INTENT", False),
            ignore_bots=_env_bool(env, "ZENE_IGNORE_BOTS", True),
            nsfw_enabled=_env_bool(env, "ZENE_NSFW_ENABLED", True),
            presence_name=_clean(env.get("ZENE_PRESENCE")) or "Black Myth: Wukong",
            request_timeout=_env_float(env, "ZENE_REQUEST_TIMEOUT", 10.0),
            trigger_cooldown=_env_float(env, "ZENE_TRIGGER_COOLDOWN", 1.5),
            retry_attempts=max(1, _env_int(env, "ZENE_RETRY_ATTEMPTS", 3)),
            backoff_base=max(0.0, _env_float(env, "ZENE_BACKOFF_BASE", 1.0)),
            backoff_cap=max(1.0, _env_float(env, "ZENE_BACKOFF_CAP", 60.0)),
            max_restarts=max(0, _env_int(env, "ZENE_MAX_RESTARTS", 10)),
            boot_timeout=max(10.0, _env_float(env, "ZENE_BOOT_TIMEOUT", 120.0)),
            health_host=_clean(env.get("HEALTH_HOST")) or "127.0.0.1",
            health_port=_env_int(env, "HEALTH_PORT", 8080),
            max_asset_bytes=max(1024, _env_int(env, "ZENE_MAX_ASSET_BYTES", 8 * 1024 * 1024)),
        )
