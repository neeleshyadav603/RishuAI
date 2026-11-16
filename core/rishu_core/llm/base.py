"""Shared LLM types and errors. Messages use the OpenAI chat format (plain dicts)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """Base class for LLM provider errors."""


class QuotaError(LLMError):
    """HTTP 429: rate limit or free-tier quota reached."""


class AuthError(LLMError):
    """HTTP 401/403: missing or wrong API key."""


class ModelNotFound(LLMError):
    """The model ID no longer exists at this provider."""


class ProviderUnavailable(LLMError):
    """Network failure, timeout or 5xx."""


class AllProvidersFailed(LLMError):
    """No provider could answer. ``reasons`` has one short line per attempt."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons) or "no LLM provider is configured")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str | None = None


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    # Set when the router had to fall back; safe to show to the user.
    note: str | None = None

    def to_message(self) -> dict[str, Any]:
        """The assistant message to append to the conversation."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.raw_arguments or json.dumps(call.arguments),
                    },
                }
                for call in self.tool_calls
            ]
        return message


class TokenStream:
    """Receives the reply text piece by piece while the model writes it.

    ``reset`` tells the listener to discard what it got for the current reply
    (the provider failed midway and another one starts again, or the text
    turned out to be a preamble to tool calls).
    """

    def __init__(
        self, on_token: Callable[[str], None], on_reset: Callable[[], None] | None = None
    ):
        self._on_token = on_token
        self._on_reset = on_reset
        self.emitted = False

    def token(self, text: str) -> None:
        if text:
            self.emitted = True
            self._on_token(text)

    def reset(self) -> None:
        if self.emitted:
            self.emitted = False
            if self._on_reset:
                self._on_reset()


class ChatModel(Protocol):
    """Anything the agent can talk to: the router, or a scripted model in tests."""

    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: TokenStream | None = None,
    ) -> LLMResponse: ...
