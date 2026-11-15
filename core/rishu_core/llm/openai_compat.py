"""Client for any OpenAI-compatible chat API (Groq, Gemini, OpenRouter, Ollama)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import (
    AuthError,
    LLMError,
    LLMResponse,
    ModelNotFound,
    ProviderUnavailable,
    QuotaError,
    ToolCall,
)

_MODEL_GONE_HINTS = ("not found", "does not exist", "decommission", "deprecated", "unknown model")


class OpenAICompatClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def list_models(self, timeout: float | None = None) -> list[str]:
        data = self._request("GET", "models", timeout=timeout)
        return [
            item["id"] for item in data.get("data", []) if isinstance(item, dict) and "id" in item
        ]

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.4,
    ) -> LLMResponse:
        body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = self._request("POST", "chat/completions", json=body)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name}: unexpected response shape") from exc
        calls = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function") or {}
            raw_args = function.get("arguments") or "{}"
            parse_error = None
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except (ValueError, TypeError) as exc:
                args, parse_error = {}, str(exc)
            calls.append(
                ToolCall(
                    id=raw.get("id") or f"call_{index}",
                    name=function.get("name") or "",
                    arguments=args,
                    raw_arguments=raw_args if isinstance(raw_args, str) else json.dumps(raw_args),
                    parse_error=parse_error,
                )
            )
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=calls,
            provider=self.name,
            model=data.get("model") or model,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("timeout") is None:
            kwargs.pop("timeout", None)
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name}: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            self._raise_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailable(f"{self.name}: response was not JSON") from exc
        if not isinstance(data, dict):
            raise LLMError(f"{self.name}: unexpected response shape")
        return data

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        text = response.text[:300].lower()
        if status == 429:
            raise QuotaError(f"{self.name}: rate limit or quota reached (429)")
        if status in (401, 403):
            raise AuthError(f"{self.name}: API key missing or rejected ({status})")
        if status == 404 or (
            status == 400 and "model" in text and any(h in text for h in _MODEL_GONE_HINTS)
        ):
            raise ModelNotFound(f"{self.name}: model not available ({status})")
        if status >= 500:
            raise ProviderUnavailable(f"{self.name}: server error ({status})")
        raise LLMError(f"{self.name}: request rejected ({status})")
