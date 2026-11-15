"""A scripted model for tests: replays fixed replies and tool calls."""

from __future__ import annotations

import copy
import json
from typing import Any

from .base import LLMResponse, ToolCall

Step = str | list[dict[str, Any]] | Exception


class ScriptedLLM:
    """Each ``chat`` call consumes one step.

    A step is a final reply (``str``), a list of tool calls
    (``[{"name": ..., "arguments": {...}}]``), or an exception to raise.
    """

    def __init__(self, script: list[Step]):
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self, role: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        self.calls.append({"role": role, "messages": copy.deepcopy(messages), "tools": tools})
        if not self._script:
            raise AssertionError("ScriptedLLM ran out of steps")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            return LLMResponse(content=step, provider="mock", model="scripted")
        calls = [
            ToolCall(
                id=f"call_{len(self.calls)}_{index}",
                name=item["name"],
                arguments=dict(item.get("arguments", {})),
                raw_arguments=json.dumps(item.get("arguments", {})),
                parse_error=item.get("parse_error"),
            )
            for index, item in enumerate(step)
        ]
        return LLMResponse(tool_calls=calls, provider="mock", model="scripted")
