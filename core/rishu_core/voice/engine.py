"""Shared voice parts for the whole core: synthesizer, player, transcriber factory."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

from .mic import Recorder, SourceFactory, mic_available
from .player import Player, default_player
from .stt import GroqTranscriber, SttError
from .tts import ChainSynthesizer, EdgeSynthesizer, SapiSynthesizer, Synthesizer, default_workdir


class VoiceEngine:
    def __init__(
        self,
        voice_cfg: Mapping[str, Any],
        speech_cfg: Mapping[str, Any],
        providers_cfg: Mapping[str, Any],
        key_for: Callable[[str], str],
        *,
        home: Path,
        synthesizer: Synthesizer | None = None,
        player: Player | None = None,
        mic_source: SourceFactory | None = None,
        mic_check: Callable[[], tuple[bool, str]] = mic_available,
        transport: httpx.BaseTransport | None = None,
    ):
        self.cfg = voice_cfg
        self.speech_cfg = speech_cfg
        self.providers_cfg = providers_cfg
        self._key_for = key_for
        self.home = home
        self.workdir = default_workdir()
        if synthesizer is None:
            chain: list[Synthesizer] = []
            if voice_cfg.get("edge_tts", True):
                chain.append(
                    EdgeSynthesizer(
                        voice_cfg.get("edge_voices", {}), str(voice_cfg.get("rate", "+0%"))
                    )
                )
            chain.append(SapiSynthesizer(home / "voice"))
            synthesizer = ChainSynthesizer(chain)
        self.synthesizer = synthesizer
        self.player = player or default_player()
        self._mic_source = mic_source
        self._mic_check = mic_check
        self._transport = transport
        self._mic_status: tuple[bool, str] | None = None

    # ---- capabilities --------------------------------------------------

    def stt_provider(self) -> tuple[str, Mapping[str, Any]]:
        name = str(self.speech_cfg.get("stt_provider", "groq"))
        return name, self.providers_cfg.get(name) or {}

    def stt_key(self) -> str:
        name, cfg = self.stt_provider()
        return self._key_for(name) if cfg else ""

    def mic(self, refresh: bool = False) -> tuple[bool, str]:
        if self._mic_source is not None:
            return True, ""
        if self._mic_status is None or refresh:
            self._mic_status = self._mic_check()
        return self._mic_status

    def status(self, refresh: bool = False) -> dict[str, Any]:
        mic_ok, mic_reason = self.mic(refresh)
        has_key = bool(self.stt_key())
        if not mic_ok:
            input_reason = mic_reason
        elif not has_key:
            input_reason = "needs a Groq API key"
        else:
            input_reason = ""
        output = self.player.available() and self.synthesizer.available()
        return {
            "input": mic_ok and has_key,
            "input_reason": input_reason,
            "output": output,
            "output_reason": "" if output else "no voice output on this device",
            "hotkey": str(self.cfg.get("hotkey_label", "")),
        }

    # ---- parts ---------------------------------------------------------

    def new_recorder(self) -> Recorder:
        mic = self.cfg.get("mic", {})
        return Recorder(
            self._mic_source,
            silence_seconds=float(mic.get("silence_seconds", 1.2)),
            no_speech_seconds=float(mic.get("no_speech_seconds", 7)),
            max_seconds=float(mic.get("max_seconds", 30)),
        )

    def transcriber(self) -> GroqTranscriber:
        name, cfg = self.stt_provider()
        if not cfg:
            raise SttError("error", f"Speech provider '{name}' is not configured.")
        return GroqTranscriber(
            cfg["base_url"],
            self.stt_key(),
            list(self.speech_cfg.get("stt_models") or []),
            transport=self._transport,
        )
