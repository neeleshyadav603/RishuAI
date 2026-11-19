"""Speech to text through Groq's free Whisper API (OpenAI-compatible endpoint)."""

from __future__ import annotations

from collections.abc import Sequence

import httpx


class SttError(Exception):
    """Transcription failed. ``code``: no_key, auth, quota, unreachable, error."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class GroqTranscriber:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        models: Sequence[str],
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise SttError("no_key", "Voice input needs a Groq API key.")
        if not models:
            raise SttError("error", "No speech-to-text model is configured.")
        self.models = list(models)
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def transcribe(self, wav: bytes, language: str | None = None, prompt: str = "") -> str:
        last: SttError | None = None
        for model in self.models:
            data = {"model": model, "response_format": "json", "temperature": "0"}
            if language:
                data["language"] = language
            if prompt:
                data["prompt"] = prompt
            try:
                response = self._http.post(
                    "audio/transcriptions",
                    data=data,
                    files={"file": ("speech.wav", wav, "audio/wav")},
                )
            except httpx.HTTPError as exc:
                raise SttError(
                    "unreachable", f"Speech service not reachable ({type(exc).__name__})."
                ) from exc
            status = response.status_code
            if status == 200:
                try:
                    return str(response.json().get("text", "")).strip()
                except ValueError as exc:
                    raise SttError("error", "Speech service sent an unreadable answer.") from exc
            if status in (401, 403):
                raise SttError("auth", "The Groq API key was rejected.")
            if status == 429:
                raise SttError("quota", "The free speech quota is used up for now (429).")
            if status in (400, 404) and "model" in response.text.lower():
                last = SttError("error", f"Speech model '{model}' is not available.")
                continue  # try the next configured model
            raise SttError("error", f"Speech service refused the request ({status}).")
        raise last or SttError("error", "No speech model worked.")
