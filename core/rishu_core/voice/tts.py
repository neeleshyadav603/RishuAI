"""Text to speech.

1. Microsoft Edge neural voices through the free ``edge-tts`` package (online,
   natural Hindi and Indian-English voices). Behind the ``voice.edge_tts``
   setting because the service is not an official public API.
2. Windows' built-in SAPI voices through PowerShell's System.Speech (offline,
   always available on Windows 10/11, no extra install).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .text import is_devanagari

CREATE_NO_WINDOW = 0x08000000


class TtsError(Exception):
    pass


@dataclass
class Audio:
    path: Path
    kind: str  # "mp3" or "wav"


class Synthesizer(Protocol):
    name: str

    def available(self) -> bool: ...

    def synth(self, text: str, gender: str, out_dir: Path) -> Audio: ...


def _voice_for(voices: Mapping[str, Any], text: str, gender: str) -> str:
    table = voices.get(gender) or voices.get("male") or {}
    key = "devanagari" if is_devanagari(text) else "latin"
    return str(table.get(key) or "")


class EdgeSynthesizer:
    name = "edge"

    def __init__(self, voices: Mapping[str, Any], rate: str = "+0%", timeout: float = 20.0):
        self.voices = voices
        self.rate = rate
        self.timeout = timeout

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    def synth(self, text: str, gender: str, out_dir: Path) -> Audio:
        import edge_tts

        voice = _voice_for(self.voices, text, gender)
        if not voice:
            raise TtsError("no edge voice configured")

        async def run() -> bytes:
            communicate = edge_tts.Communicate(text, voice, rate=self.rate)
            chunks = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            data = asyncio.run(asyncio.wait_for(run(), self.timeout))
        except Exception as exc:  # noqa: BLE001 - network, service and timeout errors
            raise TtsError(f"edge-tts failed: {type(exc).__name__}") from exc
        if len(data) < 200:
            raise TtsError("edge-tts returned no audio")
        path = out_dir / f"tts-{uuid.uuid4().hex[:10]}.mp3"
        path.write_bytes(data)
        return Audio(path, "mp3")


_SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$text = [IO.File]::ReadAllText($args[0], [Text.Encoding]::UTF8)
$culture = $args[2]
$gender = $args[3]
$voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled })
$pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -eq $culture -and $_.VoiceInfo.Gender -eq $gender } | Select-Object -First 1
if (-not $pick) { $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -eq $culture } | Select-Object -First 1 }
if (-not $pick) { $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' -and $_.VoiceInfo.Gender -eq $gender } | Select-Object -First 1 }
if ($pick) { $s.SelectVoice($pick.VoiceInfo.Name) }
$s.SetOutputToWaveFile($args[1])
$s.Speak($text)
$s.Dispose()
"""

Runner = Callable[..., subprocess.CompletedProcess]


class SapiSynthesizer:
    """Offline Windows voices. Hindi needs the Windows Hindi speech pack; otherwise
    an English voice reads the text."""

    name = "sapi"

    def __init__(
        self, script_dir: Path, *, platform: str = sys.platform, run: Runner = subprocess.run
    ):
        self.script_dir = script_dir
        self.platform = platform
        self._run = run

    def available(self) -> bool:
        return self.platform == "win32"

    def synth(self, text: str, gender: str, out_dir: Path) -> Audio:
        if not self.available():
            raise TtsError("Windows voices are only available on Windows")
        self.script_dir.mkdir(parents=True, exist_ok=True)
        script = self.script_dir / "rishu_sapi.ps1"
        if not script.exists() or script.read_text(encoding="utf-8") != _SAPI_SCRIPT:
            script.write_text(_SAPI_SCRIPT, encoding="utf-8")
        stem = uuid.uuid4().hex[:10]
        text_file = out_dir / f"tts-{stem}.txt"
        wav = out_dir / f"tts-{stem}.wav"
        text_file.write_text(text, encoding="utf-8")
        culture = "hi-IN" if is_devanagari(text) else "en-IN"
        try:
            result = self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    str(text_file),
                    str(wav),
                    culture,
                    "Female" if gender == "female" else "Male",
                ],
                capture_output=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TtsError(f"Windows voice failed: {type(exc).__name__}") from exc
        finally:
            text_file.unlink(missing_ok=True)
        if result.returncode != 0 or not wav.exists() or wav.stat().st_size < 100:
            raise TtsError("Windows voice produced no audio")
        return Audio(wav, "wav")


class ChainSynthesizer:
    """Try each synthesizer in order; remember which one worked last."""

    def __init__(self, synthesizers: list[Synthesizer]):
        self.synthesizers = synthesizers
        self.last_used = ""
        self.last_error = ""

    @property
    def name(self) -> str:
        return "+".join(s.name for s in self.synthesizers)

    def available(self) -> bool:
        return any(s.available() for s in self.synthesizers)

    def synth(self, text: str, gender: str, out_dir: Path) -> Audio:
        errors = []
        for synth in self.synthesizers:
            if not synth.available():
                continue
            try:
                audio = synth.synth(text, gender, out_dir)
            except TtsError as exc:
                errors.append(str(exc))
                continue
            self.last_used = synth.name
            return audio
        self.last_error = "; ".join(errors) or "no voice available"
        raise TtsError(self.last_error)


def default_workdir() -> Path:
    path = Path(tempfile.gettempdir()) / "rishu-voice"
    path.mkdir(parents=True, exist_ok=True)
    return path
