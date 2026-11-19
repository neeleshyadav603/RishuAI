"""Record one spoken request from the microphone, ending on silence.

Uses ``sounddevice`` (PortAudio; its Windows wheel ships the DLL). Audio is
16 kHz mono 16-bit, the format Whisper expects.
"""

from __future__ import annotations

import io
import math
import queue
import threading
import wave
from array import array
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

RATE = 16_000
BLOCK = 1_600  # 100 ms

# A source yields raw PCM blocks until closed. Real: microphone. Tests: a list.
SourceFactory = Callable[[], AbstractContextManager[Iterator[bytes]]]


class MicError(Exception):
    pass


def rms(block: bytes) -> float:
    samples = array("h")
    samples.frombytes(block[: len(block) - len(block) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def level_of(value: float) -> float:
    """Map RMS to 0..1 on a log scale for the orb animation."""
    if value <= 50:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(value / 50)) / 50))


def to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buffer.getvalue()


@dataclass
class Recording:
    pcm: bytes
    heard_speech: bool
    cancelled: bool
    # Exact digital silence: Windows sends zeros when its privacy setting
    # blocks desktop apps from the microphone, or the mic is muted in hardware.
    silent: bool = False

    @property
    def seconds(self) -> float:
        return len(self.pcm) / 2 / RATE


class _MicSource:
    def __init__(self) -> None:
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream: Any = None

    def __enter__(self) -> Iterator[bytes]:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise MicError("Microphone support is not installed.") from exc

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            self._queue.put(bytes(indata))

        try:
            self._stream = sd.RawInputStream(
                samplerate=RATE, blocksize=BLOCK, channels=1, dtype="int16", callback=callback
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - PortAudio raises its own error types
            raise MicError("No microphone found, or it is in use by another app.") from exc
        return self._blocks()

    def _blocks(self) -> Iterator[bytes]:
        while True:
            try:
                yield self._queue.get(timeout=2.0)
            except queue.Empty as exc:
                raise MicError("The microphone stopped sending audio.") from exc

    def __exit__(self, *exc: object) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001, S110 - closing a broken stream
                pass


def mic_available() -> tuple[bool, str]:
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return False, "microphone support is not installed"
    try:
        device = sd.query_devices(kind="input")
    except Exception:  # noqa: BLE001
        return False, "no microphone found"
    if not device or int(device.get("max_input_channels", 0)) < 1:
        return False, "no microphone found"
    return True, ""


class Recorder:
    def __init__(
        self,
        source: SourceFactory | None = None,
        *,
        silence_seconds: float = 1.2,
        no_speech_seconds: float = 7.0,
        max_seconds: float = 30.0,
    ):
        self._source = source or _MicSource
        self.silence_blocks = max(1, round(silence_seconds * 10))
        self.no_speech_blocks = max(1, round(no_speech_seconds * 10))
        self.max_blocks = max(1, round(max_seconds * 10))
        self._finish = threading.Event()
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._lock.locked()

    def finish(self) -> None:
        """The user is done speaking: stop and transcribe what was heard."""
        self._finish.set()

    def cancel(self) -> None:
        """Throw the recording away."""
        self._cancel.set()

    def record(self, on_level: Callable[[float], None] | None = None) -> Recording:
        if not self._lock.acquire(blocking=False):
            raise MicError("Already listening.")
        self._finish.clear()
        self._cancel.clear()
        try:
            return self._record(on_level)
        finally:
            self._lock.release()

    def _record(self, on_level: Callable[[float], None] | None) -> Recording:
        blocks: list[bytes] = []
        floor: float | None = None
        heard = False
        quiet = 0
        peak = 0.0
        with self._source() as source:
            for count, block in enumerate(source, 1):
                if self._cancel.is_set():
                    return Recording(b"", False, True)
                blocks.append(block)
                energy = rms(block)
                if on_level:
                    on_level(level_of(energy))
                if count <= 3:  # the first 300 ms set the noise floor
                    floor = energy if floor is None else min(floor, energy)
                    if count < 3:
                        continue
                # The cap matters when the user starts talking at once: the
                # "noise floor" is then speech, and must not hide it.
                threshold = max(300.0, min((floor or 0.0) * 2.5, 1200.0))
                peak = max(peak, energy)
                if energy >= threshold:
                    heard = True
                    quiet = 0
                elif heard:
                    quiet += 1
                if self._finish.is_set():
                    break
                if heard and quiet >= self.silence_blocks:
                    break
                if not heard and count >= self.no_speech_blocks:
                    break
                if count >= self.max_blocks:
                    break
        if self._cancel.is_set():
            return Recording(b"", False, True)
        if self._finish.is_set() and peak >= 200.0:
            heard = True  # the user said they were done: trust that they spoke
        silent = not heard and len(blocks) >= 3 and max(rms(b) for b in blocks) < 2.0
        return Recording(b"".join(blocks), heard, False, silent)
