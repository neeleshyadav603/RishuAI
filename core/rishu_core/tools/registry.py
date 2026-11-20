"""Tool definitions and the registry the agent calls into."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..permissions import Risk

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


@dataclass
class ToolResult:
    ok: bool
    content: str
    # True when the content comes from outside (web, files, messages): it is
    # data, never instructions, and taints the rest of the turn.
    untrusted: bool = False
    source: str = ""
    data: Any = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: Risk
    handler: Callable[..., ToolResult]
    untrusted_output: bool = False
    risk_fn: Callable[[dict[str, Any]], Risk] | None = None
    preview_fn: Callable[[dict[str, Any]], str] | None = None
    skill: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def risk_for(self, args: dict[str, Any]) -> Risk:
        return self.risk_fn(args) if self.risk_fn else self.risk

    def preview(self, args: dict[str, Any]) -> str:
        """Plain-language description of exactly what will happen."""
        if self.preview_fn:
            return self.preview_fn(args)
        shown = ", ".join(f"{key}={value!r}" for key, value in args.items())
        return f"{self.name}({shown})"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def clean_args(self, args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Drop unknown keys and check required keys and basic types."""
        props = self.parameters.get("properties", {})
        cleaned = {key: value for key, value in args.items() if key in props}
        for key in self.parameters.get("required", []):
            if key not in cleaned:
                return cleaned, f"missing required argument '{key}'"
        for key, value in cleaned.items():
            expected = _JSON_TYPES.get(props[key].get("type", ""), ())
            wrong_bool = isinstance(value, bool) and bool not in expected
            if expected and (not isinstance(value, expected) or wrong_bool):
                return cleaned, f"argument '{key}' must be {props[key]['type']}"
        return cleaned, None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        # Shared stores that the runtime and the system prompt read as well.
        self.reminders: Any = None
        self.memory: Any = None
        self.browser: Any = None
        self.teach: Any = None

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[name].schema() for name in self.names()]
