"""Speak a reply sentence by sentence; the next sentence is prepared while one plays."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

from .player import Player
from .text import clean_for_speech, split_for_speech
from .tts import Audio, Synthesizer, TtsError

_DONE = object()


class Speaker:
    def __init__(
        self,
        synthesizer: Synthesizer,
        player: Player,
        workdir: Path,
        on_state: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        max_chars: int = 2500,
    ):
        self.synthesizer = synthesizer
        self.player = player
        self.workdir = workdir
        self.on_state = on_state
        self.on_error = on_error
        self.max_chars = max_chars
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def available(self) -> bool:
        return self.player.available() and self.synthesizer.available()

    @property
    def speaking(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def say(self, text: str, gender: str = "male") -> bool:
        """Start speaking ``text`` (stops anything already being said)."""
        if not self.available():
            return False
        cleaned = clean_for_speech(text)[: self.max_chars]
        chunks = split_for_speech(cleaned)
        if not chunks:
            return False
        self.stop()
        with self._lock:
            cancel = threading.Event()
            self._cancel = cancel
            thread = threading.Thread(target=self._run, args=(chunks, gender, cancel), daemon=True)
            self._thread = thread
            thread.start()
        return True

    def stop(self, wait: float = 2.0) -> None:
        with self._lock:
            self._cancel.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=wait)

    def wait(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(self, chunks: list[str], gender: str, cancel: threading.Event) -> None:
        ready: queue.Queue[object] = queue.Queue(maxsize=2)

        def put(item: object) -> bool:
            while not cancel.is_set():
                try:
                    ready.put(item, timeout=0.2)
                    return True
                except queue.Full:
                    continue
            return False

        def produce() -> None:
            for chunk in chunks:
                if cancel.is_set():
                    return
                try:
                    audio = self.synthesizer.synth(chunk, gender, self.workdir)
                except TtsError as exc:
                    put(exc)
                    return
                if not put(audio):
                    audio.path.unlink(missing_ok=True)
                    return
            put(_DONE)

        threading.Thread(target=produce, daemon=True).start()
        started = False
        try:
            while not cancel.is_set():
                try:
                    item = ready.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is _DONE:
                    break
                if isinstance(item, TtsError):
                    if self.on_error:
                        self.on_error(str(item))
                    break
                assert isinstance(item, Audio)
                if not started:
                    started = True
                    if self.on_state:
                        self.on_state("speaking")
                try:
                    self.player.play(item.path, item.kind, cancel)
                finally:
                    item.path.unlink(missing_ok=True)
        finally:
            if self.on_state and not cancel.is_set():
                self.on_state("idle")
            # Clean up audio that was prepared but not played.
            while True:
                try:
                    item = ready.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, Audio):
                    item.path.unlink(missing_ok=True)
