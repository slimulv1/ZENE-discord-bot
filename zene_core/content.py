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
MESSAGES: dict[str, str] = DATA["text_triggers"]
FOLO_TEXT: str = DATA["contains_triggers"][0]["response"]["value"]
CODE_STORIES: list[str] = DATA["choice_triggers"]["300 bài code thiếu nhi"]
COMMAND_TEXTS: dict[str, str] = DATA["command_texts"]
ANXIN_STORIES: list[str] = DATA["anxin_stories"]


def build_registry() -> TriggerRegistry:
    registry = TriggerRegistry()

    for phrase, text in MESSAGES.items():
        registry.add(
            Trigger(
                name=f"text:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("text", text),
            )
        )

    for spec in DATA["contains_triggers"]:
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

    for phrase, folder in DATA["folder_triggers"].items():
        registry.add(
            Trigger(
                name=f"folder:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("folder", folder),
            )
        )

    for phrase, choices in DATA["choice_triggers"].items():
        registry.add(
            Trigger(
                name=f"choice:{phrase}",
                kind="exact",
                pattern=phrase,
                payload=Response("choice", tuple(choices)),
            )
        )

    return registry.finalize()
