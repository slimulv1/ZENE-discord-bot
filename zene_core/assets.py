"""Immutable, cached asset access.

Key fixes over the legacy cog:
* Excel is parsed ONCE at boot instead of on every incoming message.
* Paths are resolved against the project root and traversal is rejected.
* Sending uses in-memory bytes, so two concurrent commands can never corrupt
  a shared ``cache.jpg`` and no file descriptor is left open.
"""

from __future__ import annotations

import asyncio
import logging
import random
import unicodedata
from io import BytesIO
from pathlib import Path

log = logging.getLogger(__name__)

_IMAGE_FOLDERS = ("haohan", "xaolon", "auzam", "no_horny", "bonk", "tv")


class AssetRegistry:
    def __init__(
        self,
        root: Path,
        data_dir: Path,
        max_asset_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self.root = root.resolve()
        self.data_dir = data_dir.resolve()
        self.max_asset_bytes = max_asset_bytes
        self._by_command: dict[str, str] = {}
        self._folders: dict[str, list[str]] = {}
        self._rng = random.SystemRandom()
        self.loaded = False

    @staticmethod
    def _norm(value: str) -> str:
        return unicodedata.normalize("NFC", str(value or "")).strip().lower()

    def load(self) -> None:
        """Synchronous by design — call via ``asyncio.to_thread`` at boot."""
        self._by_command.clear()
        self._folders.clear()

        excel = self.data_dir / "command_data" / "command_link.xlsx"
        if excel.is_file():
            try:
                import pandas as pd

                frame = pd.read_excel(excel, dtype=str).fillna("")
                commands = frame.get("Command", [])
                locations = frame.get("File_Location", [])
                for command, location in zip(commands, locations, strict=False):
                    key = self._norm(command)
                    rel = str(location).strip().replace("\\", "/")
                    if key and rel:
                        self._by_command[key] = rel
                log.info("asset registry: %d command mappings từ Excel", len(self._by_command))
            except Exception as exc:  # noqa: BLE001 - optional dependency boundary
                log.warning("Không đọc được command_link.xlsx: %s", exc)
        else:
            log.warning("Thiếu %s — bỏ qua mapping Excel", excel)

        for name in _IMAGE_FOLDERS:
            folder = self.data_dir / "image" / name
            if not folder.is_dir():
                continue
            try:
                self._folders[name] = [
                    str(child.relative_to(self.root)).replace("\\", "/")
                    for child in folder.iterdir()
                    if child.is_file()
                ]
            except OSError as exc:
                log.warning("Không liệt kê được %s: %s", folder, exc)
        self.loaded = True

    def path_for(self, relative: str) -> Path | None:
        """Resolve a repo-relative asset path; reject traversal and missing files."""
        if not relative:
            return None
        candidate = (self.root / str(relative)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            log.warning("Từ chối đường dẫn asset ngoài project: %r", relative)
            return None
        return candidate if candidate.is_file() else None

    def file_for_command(self, command: str) -> str | None:
        return self._by_command.get(self._norm(command))

    def random_in(self, folder: str) -> str | None:
        items = self._folders.get(folder) or []
        return self._rng.choice(items) if items else None

    @property
    def command_count(self) -> int:
        return len(self._by_command)

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_command))

    async def read_bytes(self, relative: str) -> bytes | None:
        path = self.path_for(relative)
        if path is None:
            return None
        try:
            size = path.stat().st_size
            if size > self.max_asset_bytes:
                log.warning("Asset quá lớn, bỏ qua: %s (%d bytes)", relative, size)
                return None
            return await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            log.warning("Không đọc được asset %s: %s", relative, exc)
            return None

    async def discord_file(self, relative: str, filename: str | None = None):
        """Build a ``discord.File`` from memory — no open handles, no shared file."""
        data = await self.read_bytes(relative)
        if data is None:
            return None
        import discord  # lazy: keeps pure modules importable without discord.py

        path = Path(relative)
        return discord.File(BytesIO(data), filename=filename or path.name)

    async def composite_avatar(
        self,
        base_relative: str,
        avatar_bytes: bytes,
        box: tuple[int, int],
        size: tuple[int, int] = (256, 256),
        mask: str | None = "ellipse",
    ) -> BytesIO | None:
        """Paste a member avatar onto a base image, entirely in memory.

        Quality pipeline (Pillow): EXIF-oriented base -> high-quality LANCZOS
        fit -> mild unsharp -> soft-edged elliptical mask -> lossless PNG.
        """

        def work() -> BytesIO | None:
            try:
                from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
            except ImportError:
                log.warning("Thiếu Pillow — bỏ qua lệnh composite avatar")
                return None
            base_path = self.path_for(base_relative)
            if base_path is None:
                return None
            try:
                with Image.open(base_path) as raw_base:
                    base = ImageOps.exif_transpose(raw_base).convert("RGBA")
                with Image.open(BytesIO(avatar_bytes)) as raw_avatar:
                    avatar = ImageOps.exif_transpose(raw_avatar).convert("RGBA")

                # Preserve aspect ratio, crop to the exact box, resample well.
                avatar = ImageOps.fit(
                    avatar, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
                )
                avatar = avatar.filter(ImageFilter.UnsharpMask(radius=1, percent=70, threshold=3))

                if mask == "ellipse":
                    shape = Image.new("L", size, 0)
                    draw = ImageDraw.Draw(shape)
                    draw.ellipse((1, 1, size[0] - 2, size[1] - 2), fill=255)
                    shape = shape.filter(ImageFilter.GaussianBlur(2))
                    blend = ImageChops.multiply(avatar.getchannel("A"), shape)
                else:
                    blend = avatar.getchannel("A")

                base.paste(avatar, box, blend)
                output = BytesIO()
                base.convert("RGB").save(output, format="PNG", optimize=True)
                output.seek(0)
                return output
            except Exception as exc:  # noqa: BLE001 - malformed avatar must not crash
                log.warning("Composite avatar thất bại: %s", exc)
                return None

        return await asyncio.to_thread(work)
