"""The user's own settings, stored in the data folder as ``settings.json``.

Only the keys listed in ``_FIELDS`` can be set, and each value is validated.
These settings are changed by the user in the app (through the local API),
never by the model and never by content the model reads.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .permissions import AUTONOMY_MODES

LANGUAGES = ("auto", "hi", "en", "hinglish")
SCRIPTS = ("roman", "devanagari")
VOICE_GENDERS = ("male", "female")


def _choice(options: tuple[str, ...]) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        if value not in options:
            raise ValueError(f"must be one of: {', '.join(options)}")
        return value

    return check


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("must be text")
    # One line, printable: the name is placed in the system prompt.
    cleaned = " ".join("".join(ch for ch in value if ch.isprintable()).split())
    if len(cleaned) > 60:
        raise ValueError("must be 60 characters or fewer")
    return cleaned


def _flag(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("must be true or false")
    return value


_FIELDS: dict[str, Callable[[Any], Any]] = {
    "user_name": _name,
    "language": _choice(LANGUAGES),
    "script": _choice(SCRIPTS),
    "autonomy": _choice(AUTONOMY_MODES),
    "streaming": _flag,
    "speak_replies": _flag,
    "voice_gender": _choice(VOICE_GENDERS),
}


class UserSettings:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        """Stored values; anything unknown or invalid in the file is ignored."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        clean: dict[str, Any] = {}
        for key, check in _FIELDS.items():
            if key in raw:
                try:
                    clean[key] = check(raw[key])
                except ValueError:
                    continue
        return clean

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Validate and save ``patch``. Raises ``ValueError`` naming the bad key."""
        if not isinstance(patch, dict):
            raise ValueError("settings must be an object")
        checked: dict[str, Any] = {}
        for key, value in patch.items():
            check = _FIELDS.get(key)
            if check is None:
                raise ValueError(f"unknown setting '{key}'")
            try:
                checked[key] = check(value)
            except ValueError as exc:
                raise ValueError(f"{key}: {exc}") from exc
        with self._lock:
            data = {**self.load(), **checked}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
        return data
