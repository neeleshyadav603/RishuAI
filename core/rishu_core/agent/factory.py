"""Wire settings, router, tools and permissions into a ready agent."""

from __future__ import annotations

import platform
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..activity_log import ActivityLog
from ..config import Settings, data_dir, load_settings, read_prompt
from ..llm import ChatModel, LLMRouter
from ..permissions import PermissionEngine
from ..tools import ToolRegistry, build_registry
from .loop import Agent, Approver

_LANGUAGE_HINT = {
    "hi": "Reply in Hindi.",
    "en": "Reply in English.",
    "hinglish": "Reply in Hinglish (Hindi in Roman script mixed with English).",
}


def build_system_prompt(settings: Settings) -> str:
    defaults = settings.defaults
    context = [f"- Device: {platform.system() or 'unknown'} computer."]
    if defaults.get("user_name"):
        context.append(f"- The user's name is {defaults['user_name']}.")
    language = defaults.get("language", "auto")
    if language in _LANGUAGE_HINT:
        context.append(f"- {_LANGUAGE_HINT[language]}")
    if defaults.get("script") == "devanagari":
        context.append("- Write Hindi in Devanagari script.")
    if defaults.get("speak_replies") is not False:
        context.append(
            "- Your replies are also read aloud by a voice. Use short, natural spoken "
            "sentences. Avoid tables, long lists and symbols unless the user asks for "
            "detail; when teaching, explain step by step in small parts."
        )
    return "\n\n".join(
        [
            read_prompt("persona_rishu", settings.root),
            read_prompt("system_rules", settings.root),
            "Context\n" + "\n".join(context),
        ]
    )


def build_agent(
    settings: Settings | None = None,
    *,
    approver: Approver | None = None,
    llm: ChatModel | None = None,
    registry: ToolRegistry | None = None,
    autonomy: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    use_router: bool = True,
    home: Path | None = None,
    streaming: bool = False,
) -> Agent:
    settings = settings or load_settings()
    if llm is None and use_router:
        router = LLMRouter.from_settings(settings.models)
        llm = router if router.providers else None
    home = home or data_dir()
    language = settings.defaults.get("language", "auto")
    return Agent(
        llm,
        registry or build_registry(settings, home=home),
        PermissionEngine(settings.policy, autonomy),
        approver,
        system_prompt=build_system_prompt(settings),
        activity_log=ActivityLog(home / "activity.jsonl"),
        max_steps=int(settings.policy.get("agent", {}).get("max_steps", 8)),
        max_history=int(settings.defaults.get("history", {}).get("max_messages", 24)),
        language="en" if language == "en" else "hinglish",
        on_event=on_event,
        streaming=streaming,
    )
