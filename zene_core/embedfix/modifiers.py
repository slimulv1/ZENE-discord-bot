"""Bộ dò modifier cho từng link.

Tiếng Việt: modifier nằm NGOÀI link (không trong query, tránh hỏng URL);
`||` spoiler, `~` hide_quote, `文` dịch,
`^` parent, `xx:` ngôn ngữ; không sửa URL trong query.
日本語: URLの外側の修飾語。`||`ネタバレ・`~`引用非表示・`文`翻訳・`^`parent・`xx:`言語。
"""

from __future__ import annotations

import re

LINK_RE = re.compile(r"https?://[^\s<>]+", re.I)
MOD_MAP = {
    "文": "translate",
    "~": "hide_quote",
    "||": "spoiler",
    "^": "parent",
}
LANG_RE = re.compile(r"\b([a-z]{2}(?:[-_][a-zA-Z]{2})?):", re.I)


def parse_modifiers(text: str) -> tuple[str, frozenset[str], str | None]:
    """Return (cleaned text, modifiers, language code)."""
    outside = " ".join(LINK_RE.split(text)[::2])
    mods = {name for token, name in MOD_MAP.items() if token in outside}
    cleaned = outside
    for token in MOD_MAP:
        cleaned = cleaned.replace(token, "")
    lang = None
    match = LANG_RE.search(cleaned)
    if match:
        lang = match.group(1).lower().replace("_", "-")
        cleaned = cleaned[: match.start()] + cleaned[match.end() :]
    return cleaned.strip(), frozenset(mods), lang
