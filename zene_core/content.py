"""Meme content loaded from one JSON file.

``zene/data/memes.json`` is the single source of truth for text triggers,
folder/choice triggers and asset command mappings. Edit that file instead of
touching Python code; no spreadsheet parser is needed at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

from .triggers import Response, Trigger, TriggerRegistry

DATA_FILE = Path(__file__).resolve().parent.parent / "zene" / "data" / "memes.json"


def _load() -> dict:
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


DATA = _load()


def fresh_data() -> dict:
    """Re-read memes.json so commands always see the latest edits."""
    try:
        return _load()
    except (OSError, ValueError, TypeError):
        return DATA


# Sections that must exist for a file to count as a valid reload. A partially
# written file is rejected so the live bot keeps its last known-good data.
_REQUIRED_SECTIONS = (
    "text_triggers",
    "contains_triggers",
    "folder_triggers",
    "choice_triggers",
    "command_texts",
    "anxin_stories",
    "assets",
)


def reload_data() -> TriggerRegistry:
    """Re-read memes.json and refresh every derived object **in place**.

    Mutating the existing containers (rather than rebinding) keeps modules that
    did ``from .content import COMMAND_TEXTS`` pointing at fresh data. Returns a
    newly built trigger registry; raises on an invalid/unreadable file so the
    caller can keep the previous data.
    """
    global DATA
    new = _load()
    if not isinstance(new, dict):
        raise ValueError("memes.json must contain an object")
    for section in _REQUIRED_SECTIONS:
        if section not in new:
            raise ValueError(f"memes.json missing section: {section}")

    DATA = new

    # Mutable containers: update in place so imported references stay valid.
    MESSAGES.clear()
    MESSAGES.update(new["text_triggers"])
    COMMAND_TEXTS.clear()
    COMMAND_TEXTS.update(new["command_texts"])
    ANXIN_STORIES[:] = new["anxin_stories"]
    stories = new["choice_triggers"].get("300 bài code thiếu nhi")
    if isinstance(stories, list):
        CODE_STORIES[:] = stories

    # Immutable strings: rebind the module global (no live importers in-repo).
    global FOLO_TEXT
    triggers = new["contains_triggers"]
    if triggers and isinstance(triggers[0], dict):
        response = triggers[0].get("response", {})
        if isinstance(response, dict):
            FOLO_TEXT = str(response.get("value", FOLO_TEXT))

    return build_registry(new)


def fresh_commands(section: str | None = None) -> list[str]:
    """Return command phrases directly from disk.

    ``section=None`` means all meme phrases; pass a section name for only that
    part (e.g. ``assets``). Invalid/missing sections degrade to the cached DATA.
    """
    data = fresh_data()
    names: set[str] = set()
    if section is not None:
        for key in data.get(section, {}):
            if isinstance(key, str) and key:
                names.add(key)
    else:
        for key in ("text_triggers", "folder_triggers", "choice_triggers", "assets"):
            for name in data.get(key, {}):
                if isinstance(name, str) and name:
                    names.add(name)
        for trigger in data.get("contains_triggers", []):
            pattern = trigger.get("pattern") if isinstance(trigger, dict) else None
            if isinstance(pattern, str) and pattern:
                names.add(pattern)
    return sorted(names)


MESSAGES: dict[str, str] = DATA["text_triggers"]
FOLO_TEXT: str = DATA["contains_triggers"][0]["response"]["value"]
CODE_STORIES: list[str] = DATA["choice_triggers"]["300 bài code thiếu nhi"]
COMMAND_TEXTS: dict[str, str] = DATA["command_texts"]
ANXIN_STORIES: list[str] = DATA["anxin_stories"]


def build_registry(data: dict | None = None) -> TriggerRegistry:
    """Build a trigger registry from ``data`` (defaults to the cached DATA)."""
    data = DATA if data is None else data
    registry = TriggerRegistry()

    for phrase, text in data["text_triggers"].items():
        registry.add(
            Trigger(
                name=f"text:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("text", text),
            )
        )

    for spec in data["contains_triggers"]:
        response = spec["response"]
        registry.add(
            Trigger(
                name=spec["name"],
                kind="contains",
                pattern=spec["pattern"],
                payload=Response(response["kind"], response["value"]),
                priority=spec.get("priority", 0),
                cooldown=spec.get("cooldown", 0.0),
            )
        )

    for phrase, folder in data["folder_triggers"].items():
        registry.add(
            Trigger(
                name=f"folder:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("folder", folder),
            )
        )

    for phrase, choices in data["choice_triggers"].items():
        registry.add(
            Trigger(
                name=f"choice:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("choice", tuple(choices)),
            )
        )

    return registry.finalize()
