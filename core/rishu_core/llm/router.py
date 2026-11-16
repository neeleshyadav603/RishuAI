"""Pick a provider and model for each request, with fallback on quota and outages."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from .base import (
    AllProvidersFailed,
    LLMError,
    LLMResponse,
    ModelNotFound,
    QuotaError,
    TokenStream,
)
from .openai_compat import OpenAICompatClient

ROLES = ("fast", "smart", "coder", "vision")
# A role with no configured model borrows from these (vision never borrows:
# a text-only model must not be handed images).
_ROLE_FALLBACK = {"fast": ("smart",), "smart": ("fast",), "coder": ("smart", "fast"), "vision": ()}


def _norm(model_id: str) -> str:
    return model_id.removeprefix("models/")


@dataclass
class ProviderState:
    name: str
    client: OpenAICompatClient
    models: dict[str, list[str]]
    local: bool = False
    discovered: list[str] | None = None
    discovery_tried: bool = False
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class LLMRouter:
    def __init__(
        self,
        providers: list[ProviderState],
        *,
        clock: Callable[[], float] = time.monotonic,
        cooldown_seconds: float = 60.0,
    ):
        self.providers = providers
        self._clock = clock
        self._cooldown = cooldown_seconds

    @classmethod
    def from_settings(
        cls,
        models_cfg: Mapping[str, Any],
        env: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        **kwargs: Any,
    ) -> LLMRouter:
        """Build from ``config/models.yaml``. Cloud providers without a key are skipped."""
        env = os.environ if env is None else env
        providers = []
        for name in models_cfg.get("order", []):
            cfg = models_cfg.get("providers", {}).get(name)
            if not cfg:
                continue
            local = bool(cfg.get("local"))
            key = env.get(cfg.get("api_key_env", ""), "") if cfg.get("api_key_env") else ""
            if not local and not key:
                continue
            client = OpenAICompatClient(name, cfg["base_url"], key or None, transport=transport)
            models = {role: list(cfg.get("models", {}).get(role) or []) for role in ROLES}
            providers.append(ProviderState(name=name, client=client, models=models, local=local))
        return cls(providers, **kwargs)

    def has_cloud_provider(self) -> bool:
        return any(not p.local for p in self.providers)

    def _discover(self, state: ProviderState) -> list[str] | None:
        """Ask the provider which models exist. Cached; ``None`` when unknown."""
        if not state.discovery_tried:
            state.discovery_tried = True
            try:
                found = state.client.list_models(timeout=3.0 if state.local else 10.0)
                state.discovered = [_norm(m) for m in found]
            except LLMError as exc:
                state.discovered = None
                if state.local:
                    # A local server that does not answer is simply not running.
                    self._cool(state, f"{state.name}: local model server not reachable")
                else:
                    state.extra["discovery_error"] = str(exc)
        return state.discovered

    def candidates(self, state: ProviderState, role: str) -> list[str]:
        configured = list(state.models.get(role) or [])
        if not configured:
            for other in _ROLE_FALLBACK.get(role, ()):
                configured = list(state.models.get(other) or [])
                if configured:
                    break
        discovered = self._discover(state)
        if discovered is None:
            return configured
        available = set(discovered)
        matched = [m for m in configured if _norm(m) in available]
        if matched:
            return matched
        if state.local and role != "vision":
            return discovered[:3]
        return configured

    def _cool(self, state: ProviderState, reason: str) -> None:
        state.cooldown_until = self._clock() + self._cooldown
        state.cooldown_reason = reason

    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: TokenStream | None = None,
    ) -> LLMResponse:
        reasons: list[str] = []
        for state in self.providers:
            if state.cooldown_until > self._clock():
                reasons.append(state.cooldown_reason or f"{state.name}: cooling down")
                continue
            models = self.candidates(state, role)
            if state.cooldown_until > self._clock():  # discovery just failed
                reasons.append(state.cooldown_reason)
                continue
            if not models:
                reasons.append(f"{state.name}: no model configured for '{role}'")
                continue
            for model in models:
                try:
                    response = state.client.chat(model, messages, tools, stream=stream)
                except LLMError as exc:
                    # A failed attempt may have streamed part of a reply: discard
                    # it before the next model or provider starts again.
                    if stream is not None:
                        stream.reset()
                    if isinstance(exc, ModelNotFound):
                        reasons.append(str(exc) + f" [{model}]")
                        continue
                    if isinstance(exc, QuotaError):
                        self._cool(state, str(exc))
                    reasons.append(str(exc))
                    break
                response.provider = state.name
                if reasons:
                    response.note = f"Using {state.name} because: " + "; ".join(reasons)
                return response
        raise AllProvidersFailed(reasons)
