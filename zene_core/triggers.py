"""Declarative message-trigger registry.

Replaces the 25-deep ``if`` chain in the legacy ``on_message`` with an O(1)
exact lookup followed by a small, pre-compiled contains/regex pass.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

Payload = Any
Fallback = Optional[Union[str, Callable[[], str]]]


@dataclass(frozen=True, slots=True)
class Response:
    kind: str  # text | choice | file | folder | composite | command
    value: Any
    filename: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Trigger:
    name: str
    kind: str  # exact | contains | regex
    pattern: str
    payload: Payload
    priority: int = 0
    cooldown: float = 0.0
    nsfw_only: bool = False


@dataclass(frozen=True, slots=True)
class TriggerMatch:
    trigger: Trigger
    groups: tuple[str, ...] = ()


def normalize(content: str) -> str:
    """NFC + lower-case so Vietnamese text matches regardless of input method."""
    return unicodedata.normalize("NFC", content or "").strip().lower()


class TriggerRegistry:
    def __init__(self) -> None:
        self._exact: dict[str, Trigger] = {}
        self._contains: list[Trigger] = []
        self._regex: list[tuple[re.Pattern[str], Trigger]] = []
        self._finalized = False

    def add(self, trigger: Trigger) -> "TriggerRegistry":
        if self._finalized:
            raise RuntimeError("Registry đã finalize; không thể thêm trigger nữa")
        if trigger.kind == "exact":
            self._exact[normalize(trigger.pattern)] = trigger
        elif trigger.kind == "contains":
            self._contains.append(trigger)
        elif trigger.kind == "regex":
            self._regex.append(
                (re.compile(trigger.pattern, re.IGNORECASE | re.DOTALL), trigger)
            )
        else:
            raise ValueError(f"Loại trigger không hợp lệ: {trigger.kind!r}")
        return self

    def finalize(self) -> "TriggerRegistry":
        self._contains.sort(key=lambda t: (-t.priority, -len(t.pattern)))
        self._regex.sort(key=lambda pair: -pair[1].priority)
        self._finalized = True
        return self

    def match(self, content: str) -> Optional[TriggerMatch]:
        normalized = normalize(content)
        if not normalized:
            return None

        exact = self._exact.get(normalized)
        if exact is not None:
            return TriggerMatch(exact)

        for trigger in self._contains:
            if normalize(trigger.pattern) in normalized:
                return TriggerMatch(trigger)

        for pattern, trigger in self._regex:
            found = pattern.search(normalized)
            if found is not None:
                return TriggerMatch(trigger, found.groups())
        return None

    @property
    def all(self) -> tuple[Trigger, ...]:
        return (
            tuple(self._exact.values())
            + tuple(self._contains)
            + tuple(trigger for _, trigger in self._regex)
        )

    def __len__(self) -> int:
        return len(self._exact) + len(self._contains) + len(self._regex)
