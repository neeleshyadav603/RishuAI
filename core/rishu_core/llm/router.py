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
    ModelFailed,
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
        # Optional: makes a shorter prompt for providers marked compact_prompt.
        self.compact: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None

    @classmethod
    def from_settings(
        cls,
        models_cfg: Mapping[str, Any],
        env: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        managed: Mapping[str, Callable[[], str | None]] | None = None,
        **kwargs: Any,
    ) -> LLMRouter:
        """Build from ``config/models.yaml``. Cloud providers without a key are skipped.

        ``managed`` maps a provider that Rishu starts itself (its offline model)
        to a function that starts it and returns its base URL, or None.
        """
        env = os.environ if env is None else env
        providers = []
        for name in models_cfg.get("order", []):
            cfg = models_cfg.get("providers", {}).get(name)
            if not cfg:
                continue
            if cfg.get("managed") and not (managed and name in managed):
                continue
            local = bool(cfg.get("local"))
            key = env.get(cfg.get("api_key_env", ""), "") if cfg.get("api_key_env") else ""
            if not local and not key:
                continue
            client = OpenAICompatClient(name, cfg["base_url"], key or None, transport=transport)
            models = {role: list(cfg.get("models", {}).get(role) or []) for role in ROLES}
            state = ProviderState(name=name, client=client, models=models, local=local)
            if cfg.get("tools_allow"):
                state.extra["tools_allow"] = set(cfg["tools_allow"])
            if cfg.get("compact_prompt"):
                state.extra["compact_prompt"] = True
            if cfg.get("managed") and managed:
                state.extra["ensure"] = managed[name]
                state.extra["transport"] = transport
            providers.append(state)
        return cls(providers, **kwargs)

    def _ready(self, state: ProviderState) -> str:
        """Start a managed provider if needed. Returns a reason when it cannot be used."""
        ensure = state.extra.get("ensure")
        if ensure is None:
            return ""
        url = ensure()
        if not url:
            return f"{state.name}: offline model not downloaded or not available"
        if state.extra.get("url") != url:
            state.client = OpenAICompatClient(
                state.name, url, None, transport=state.extra.get("transport")
            )
            state.extra["url"] = url
            state.discovery_tried, state.discovered = False, None
        return ""

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
            problem = self._ready(state)
            if problem:
                reasons.append(problem)
                continue
            models = self.candidates(state, role)
            if state.cooldown_until > self._clock():  # discovery just failed
                reasons.append(state.cooldown_reason)
                continue
            if not models:
                reasons.append(f"{state.name}: no model configured for '{role}'")
                continue
            quota_hits = 0
            offered = tools
            sent = messages
            if state.extra.get("compact_prompt") and self.compact is not None:
                sent = self.compact(messages)  # a shorter system prompt for small local models
            allow = state.extra.get("tools_allow")
            if tools and allow:
                # Small local models get only the everyday tools: a short prompt is
                # much faster on a laptop CPU and easier for them to use well.
                offered = [t for t in tools if t.get("function", {}).get("name") in allow] or None
            for model in models:
                try:
                    response = state.client.chat(model, sent, offered, stream=stream)
                except LLMError as exc:
                    # A failed attempt may have streamed part of a reply: discard
                    # it before the next model or provider starts again.
                    if stream is not None:
                        stream.reset()
                    if isinstance(exc, ModelNotFound | ModelFailed):
                        reasons.append(str(exc) + f" [{model}]")
                        continue
                    if isinstance(exc, QuotaError):
                        # Free tiers limit each model separately: try the next one.
                        quota_hits += 1
                        reasons.append(str(exc) + f" [{model}]")
                        continue
                    reasons.append(str(exc))
                    break
                response.provider = state.name
                if reasons:
                    response.note = f"Using {state.name}/{model} because: " + "; ".join(reasons)
                return response
            if quota_hits and quota_hits == len(models):
                self._cool(state, f"{state.name}: rate limit or quota reached (429)")
        raise AllProvidersFailed(reasons)
