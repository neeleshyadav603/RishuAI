"""PROTECTED MODULE (spec §3.4, §6): personal data files encrypted at rest.

Notes, memory and reminders are written through the vault. On Windows the
file content is encrypted with DPAPI for the current Windows user, so a copy
of the file is unreadable on another account or PC. Elsewhere (development
machines) files stay plain text; the caller is the same.

Files written by older versions are plain JSON: they are still read, and the
next write encrypts them.
"""

from __future__ import annotations

import base64
import os
import sys
from collections.abc import Callable
from pathlib import Path

from .secrets import _dpapi

HEADER = b"RISHU-DPAPI1\n"

Codec = Callable[..., bytes]  # codec(data, protect=bool) -> bytes


class Vault:
    def __init__(self, codec: Codec | None = None, platform: str | None = None):
        if codec is None and (platform or sys.platform) == "win32":
            codec = _dpapi
        self._codec = codec

    @property
    def encrypted(self) -> bool:
        return self._codec is not None

    def read_text(self, path: Path) -> str | None:
        """The file's text, or None if it is missing or cannot be decrypted."""
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        if not raw.startswith(HEADER):
            try:
                return raw.decode("utf-8")  # plain file from an older version
            except UnicodeDecodeError:
                return None
        if self._codec is None:
            return None
        try:
            plain = self._codec(base64.b64decode(raw[len(HEADER) :]), protect=False)
            return plain.decode("utf-8")
        except (OSError, ValueError):
            # Another Windows account or a damaged file: keep it aside, start fresh.
            try:
                os.replace(path, path.with_name(path.name + ".unreadable"))
            except OSError:
                pass
            return None

    def write_text(self, path: Path, text: str) -> None:
        data = text.encode("utf-8")
        if self._codec is not None:
            data = HEADER + base64.b64encode(self._codec(data, protect=True)) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)


_default: Vault | None = None


def default_vault() -> Vault:
    global _default
    if _default is None:
        _default = Vault()
    return _default
