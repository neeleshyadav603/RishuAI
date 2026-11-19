"""Play an audio file and stop it at any moment.

Windows: the built-in MCI service in winmm.dll (mp3 and wav, no extra install).
Elsewhere: a silent player, so the rest of the voice pipeline still runs.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from pathlib import Path
from typing import Protocol


class Player(Protocol):
    def available(self) -> bool: ...

    def play(self, path: Path, kind: str, cancel: threading.Event) -> bool:
        """Block until playback ends or ``cancel`` is set. Return False on failure."""
        ...


class NullPlayer:
    def available(self) -> bool:
        return False

    def play(self, path: Path, kind: str, cancel: threading.Event) -> bool:
        return False


class MciPlayer:
    _ids = itertools.count(1)

    def __init__(self) -> None:
        import ctypes

        self._winmm = ctypes.WinDLL("winmm")
        self._send = self._winmm.mciSendStringW
        self._buffer = ctypes.create_unicode_buffer(128)

    def available(self) -> bool:
        return True

    def _cmd(self, command: str) -> tuple[int, str]:
        code = self._send(command, self._buffer, 127, None)
        return code, self._buffer.value

    def play(self, path: Path, kind: str, cancel: threading.Event) -> bool:
        alias = f"rishu{next(self._ids)}"
        device = "mpegvideo" if kind == "mp3" else "waveaudio"
        code, _ = self._cmd(f'open "{path}" type {device} alias {alias}')
        if code != 0:
            return False
        try:
            code, _ = self._cmd(f"play {alias}")
            if code != 0:
                return False
            started = time.monotonic()
            while not cancel.is_set():
                code, mode = self._cmd(f"status {alias} mode")
                if code != 0 or (mode != "playing" and time.monotonic() - started > 0.3):
                    break
                time.sleep(0.05)
            if cancel.is_set():
                self._cmd(f"stop {alias}")
            return True
        finally:
            self._cmd(f"close {alias}")


def default_player() -> Player:
    if sys.platform == "win32":
        try:
            return MciPlayer()
        except OSError:
            pass
    return NullPlayer()
