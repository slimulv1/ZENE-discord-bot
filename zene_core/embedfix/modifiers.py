"""Per-link modifier parser.

Modifiers live in the text *around* a URL, never inside it. Parsing only the
outside text prevents a `~` or `||` in a query string from corrupting the link.
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
