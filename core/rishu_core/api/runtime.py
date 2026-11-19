"""Everything the local server shares between connections.

One :class:`CoreRuntime` lives for the whole process. It owns the settings,
the stored API keys, the LLM router and the tool registry, and builds an agent
for each app connection.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

from .. import __version__
from ..agent import Agent, Approver, build_agent
from ..config import Settings, data_dir
from ..llm import AuthError, ChatModel, LLMError, LLMRouter, ProviderUnavailable, QuotaError
from ..llm.openai_compat import OpenAICompatClient
from ..security import SecretStore, clean_secret, open_secret_store
from ..tools import ToolRegistry, build_registry
from ..user_settings import UserSettings
from ..voice import VoiceEngine

PROTOCOL_VERSION = 1
MIN_TOKEN_LENGTH = 16


class UnknownProvider(KeyError):
    pass


class CoreRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        token: str,
        home: Path | None = None,
        secrets: SecretStore | None = None,
        llm: ChatModel | None = None,
        registry: ToolRegistry | None = None,
        transport: httpx.BaseTransport | None = None,
        env: Mapping[str, str] | None = None,
        voice: VoiceEngine | None = None,
    ):
        if len(token) < MIN_TOKEN_LENGTH:
            raise ValueError("the session token is too short")
        self.token = token
        self.home = home or data_dir()
        self.base_settings = settings
        self.secrets = secrets or open_secret_store(self.home)
        self.user = UserSettings(self.home / "settings.json")
        self.registry = registry or build_registry(settings, home=self.home)
        # Sessions rebuild their agent when this number changes.
        self.generation = 0
        self._llm_override = llm  # a scripted model in tests
        self._transport = transport
        self._env = env
        self._lock = threading.Lock()
        self._router: LLMRouter | None = None
        self._router_generation = -1
        self.voice = voice or VoiceEngine(
            settings.defaults.get("voice", {}),
            settings.models.get("speech", {}),
            settings.models.get("providers", {}),
            self.key_for_provider,
            home=self.home,
            transport=transport,
        )

    # ---- settings ------------------------------------------------------

    def settings(self) -> Settings:
        overrides = {k: v for k, v in self.user.load().items() if k != "autonomy"}
        return self.base_settings.with_defaults(overrides)

    def autonomy(self) -> str:
        return self.user.load().get("autonomy") or self.base_settings.policy.get(
            "default_autonomy", "smart"
        )

    def public_settings(self) -> dict[str, Any]:
        defaults = self.settings().defaults
        return {
            "user_name": defaults.get("user_name") or "",
            "language": defaults.get("language") or "auto",
            "script": defaults.get("script") or "roman",
            "autonomy": self.autonomy(),
            "streaming": defaults.get("streaming") is not False,
            "speak_replies": defaults.get("speak_replies") is not False,
            "voice_gender": defaults.get("voice_gender") or "male",
        }

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        self.user.update(patch)
        self._changed()
        return self.public_settings()

    def server_option(self, key: str, default: float) -> float:
        return float(self.base_settings.defaults.get("server", {}).get(key, default))

    def _changed(self) -> None:
        with self._lock:
            self.generation += 1

    # ---- providers and keys --------------------------------------------

    def _provider_cfg(self, name: str) -> dict[str, Any]:
        cfg = self.base_settings.models.get("providers", {}).get(name)
        if not isinstance(cfg, dict):
            raise UnknownProvider(name)
        return cfg

    def _environment(self) -> Mapping[str, str]:
        return os.environ if self._env is None else self._env

    def _key_for(self, cfg: Mapping[str, Any]) -> tuple[str, str | None]:
        """The API key for a provider and where it came from (saved wins over env)."""
        env_name = cfg.get("api_key_env") or ""
        if not env_name:
            return "", None
        saved = self.secrets.get(env_name)
        if saved:
            return saved, "saved"
        from_env = self._environment().get(env_name, "")
        return from_env, ("env" if from_env else None)

    def key_for_provider(self, name: str) -> str:
        """The usable API key of a provider ('' when none); used by voice input."""
        cfg = self.base_settings.models.get("providers", {}).get(name)
        if not isinstance(cfg, dict):
            return ""
        return self._key_for(cfg)[0]

    def provider_env(self) -> dict[str, str]:
        """Environment for the router: real env vars plus the saved keys."""
        env = dict(self._environment())
        for cfg in self.base_settings.models.get("providers", {}).values():
            key, source = self._key_for(cfg)
            if source == "saved":
                env[cfg["api_key_env"]] = key
        return env

    def providers(self) -> list[dict[str, Any]]:
        """Provider list for the setup screen. Never includes a key."""
        result = []
        models_cfg = self.base_settings.models
        for name in models_cfg.get("order", []):
            cfg = models_cfg.get("providers", {}).get(name)
            if not cfg:
                continue
            local = bool(cfg.get("local"))
            _, source = self._key_for(cfg)
            result.append(
                {
                    "name": name,
                    "label": cfg.get("label") or name.title(),
                    "local": local,
                    "key_url": cfg.get("key_url") or "",
                    "configured": local or source is not None,
                    "key_source": source,
                }
            )
        return result

    def has_cloud_key(self) -> bool:
        return any(p["configured"] and not p["local"] for p in self.providers())

    def set_api_key(self, name: str, key: str) -> None:
        cfg = self._provider_cfg(name)
        if cfg.get("local") or not cfg.get("api_key_env"):
            raise ValueError("this provider does not use an API key")
        self.secrets.set(cfg["api_key_env"], clean_secret(key))
        self._changed()

    def delete_api_key(self, name: str) -> None:
        cfg = self._provider_cfg(name)
        if cfg.get("api_key_env"):
            self.secrets.delete(cfg["api_key_env"])
            self._changed()

    def test_provider(self, name: str, api_key: str | None = None) -> dict[str, Any]:
        """Check a key (the one given, else the stored one) by listing the models."""
        cfg = self._provider_cfg(name)
        local = bool(cfg.get("local"))
        if api_key:
            try:
                key = clean_secret(api_key)
            except ValueError:
                return {"ok": False, "code": "invalid_key"}
        else:
            key, _ = self._key_for(cfg)
        if not local and not key:
            return {"ok": False, "code": "no_key"}
        client = OpenAICompatClient(name, cfg["base_url"], key or None, transport=self._transport)
        try:
            models = client.list_models(timeout=3.0 if local else 10.0)
        except AuthError:
            return {"ok": False, "code": "auth"}
        except QuotaError:
            # The key was accepted; only the free quota is used up right now.
            return {"ok": True, "code": "quota", "models": 0}
        except ProviderUnavailable:
            return {"ok": False, "code": "unreachable"}
        except LLMError:
            return {"ok": False, "code": "error"}
        finally:
            client.close()
        return {"ok": True, "code": "ok", "models": len(models)}

    # ---- agents --------------------------------------------------------

    def llm(self) -> ChatModel | None:
        if self._llm_override is not None:
            return self._llm_override
        with self._lock:
            if self._router is None or self._router_generation != self.generation:
                self._router = LLMRouter.from_settings(
                    self.base_settings.models, env=self.provider_env(), transport=self._transport
                )
                self._router_generation = self.generation
            return self._router if self._router.providers else None

    def build_agent(self, approver: Approver, on_event: Callable[[dict[str, Any]], None]) -> Agent:
        settings = self.settings()
        return build_agent(
            settings,
            approver=approver,
            llm=self.llm(),
            registry=self.registry,
            autonomy=self.autonomy(),
            on_event=on_event,
            use_router=False,
            home=self.home,
            streaming=bool(settings.defaults.get("streaming", True)),
        )

    def hello(self) -> dict[str, Any]:
        """First event on every connection: what this core is and how it is set up."""
        return {
            "v": PROTOCOL_VERSION,
            "type": "hello",
            "protocol": PROTOCOL_VERSION,
            "version": __version__,
            "settings": self.public_settings(),
            "providers": self.providers(),
            "capabilities": {
                "step_up": False,  # arrives with the security module (Phase 3)
                "secure_store": self.secrets.kind,
                "keys_persist": bool(self.secrets.persistent),
                # How long an approval card waits before it counts as "no".
                "approval_timeout_seconds": self.server_option("approval_timeout_seconds", 120.0),
                "voice": self.voice.status(),
            },
        }
