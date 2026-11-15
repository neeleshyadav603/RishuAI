"""The agent loop: user text -> LLM -> tool calls -> permission check -> execute -> reply."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .. import offline
from ..activity_log import ActivityLog
from ..llm import AllProvidersFailed, ChatModel, LLMError, ToolCall
from ..permissions import Decision, PermissionEngine, Risk
from ..strings import t
from ..tools import ToolRegistry, ToolResult

MAX_TOOL_OUTPUT = 8000
Event = dict[str, Any]


@dataclass(frozen=True)
class ApprovalRequest:
    call_id: str
    tool: str
    args: dict[str, Any]
    risk: Risk
    decision: Decision
    preview: str
    reason: str


class Approver(Protocol):
    """How the user answers. The app implements this with cards and biometrics."""

    def confirm(self, request: ApprovalRequest) -> bool: ...

    def step_up(self, request: ApprovalRequest) -> bool: ...


class DenyAll:
    """Safe default: nothing that needs approval runs."""

    def confirm(self, request: ApprovalRequest) -> bool:
        return False

    def step_up(self, request: ApprovalRequest) -> bool:
        return False


@dataclass
class TurnResult:
    reply: str
    events: list[Event] = field(default_factory=list)
    tool_runs: list[dict[str, Any]] = field(default_factory=list)
    offline: bool = False


def wrap_untrusted(content: str, source: str) -> str:
    """Mark outside content as data so the model does not treat it as instructions."""
    safe = content.replace("</untrusted_content", "</untrusted-content")
    safe_source = source.replace('"', "'")[:200]
    return f'<untrusted_content source="{safe_source}">\n{safe}\n</untrusted_content>'


class Agent:
    def __init__(
        self,
        llm: ChatModel | None,
        registry: ToolRegistry,
        permissions: PermissionEngine,
        approver: Approver | None = None,
        *,
        system_prompt: str,
        activity_log: ActivityLog | None = None,
        max_steps: int = 8,
        role: str = "smart",
        max_history: int = 24,
        language: str = "hinglish",
        on_event: Callable[[Event], None] | None = None,
    ):
        self.llm = llm
        self.registry = registry
        self.permissions = permissions
        self.approver = approver or DenyAll()
        self.system_prompt = system_prompt
        self.log = activity_log
        self.max_steps = max_steps
        self.role = role
        self.max_history = max_history
        self.language = language
        self.on_event = on_event
        self.history: list[dict[str, Any]] = []
        self._stop = threading.Event()

    # ---- control -------------------------------------------------------

    def stop(self) -> None:
        """Emergency STOP: the running turn ends before its next step."""
        self._stop.set()

    def reset(self) -> None:
        self.history.clear()

    # ---- one user turn -------------------------------------------------

    def run_turn(self, text: str) -> TurnResult:
        self._stop.clear()
        result = TurnResult(reply="")
        emit = self._emitter(result)
        emit({"type": "state_change", "state": "thinking"})
        self.history.append({"role": "user", "content": text})
        tainted = False  # untrusted content was read earlier in this turn

        try:
            for _ in range(self.max_steps):
                if self._stop.is_set():
                    return self._finish(result, t("stopped", self.language), emit)
                if self.llm is None:
                    raise AllProvidersFailed([])
                messages = [{"role": "system", "content": self.system_prompt}, *self.history]
                response = self.llm.chat(self.role, messages, self.registry.schemas())
                if response.note:
                    emit({"type": "notice", "text": response.note})
                self.history.append(response.to_message())
                if not response.tool_calls:
                    result.reply = response.content.strip()
                    emit(
                        {
                            "type": "assistant_message",
                            "text": result.reply,
                            "provider": response.provider,
                            "model": response.model,
                        }
                    )
                    return self._finish(result, result.reply, emit, record=False)
                emit({"type": "state_change", "state": "acting"})
                for call in response.tool_calls:
                    if self._stop.is_set():
                        outcome = ToolResult(False, "Stopped by the user before this ran.")
                    else:
                        outcome = self._handle_call(call, tainted, result, emit)
                    tainted = tainted or outcome.untrusted
                    content = outcome.content[:MAX_TOOL_OUTPUT]
                    if outcome.untrusted:
                        content = wrap_untrusted(content, outcome.source or call.name)
                    self.history.append(
                        {"role": "tool", "tool_call_id": call.id, "content": content}
                    )
                emit({"type": "state_change", "state": "thinking"})
            return self._finish(result, t("max_steps", self.language), emit)
        except AllProvidersFailed as exc:
            return self._offline_turn(text, exc, result, emit)
        except LLMError as exc:
            return self._offline_turn(text, AllProvidersFailed([str(exc)]), result, emit)

    # ---- pieces --------------------------------------------------------

    def _emitter(self, result: TurnResult) -> Callable[[Event], None]:
        def emit(event: Event) -> None:
            event = {"v": 1, **event}
            result.events.append(event)
            if self.on_event:
                self.on_event(event)

        return emit

    def _finish(
        self, result: TurnResult, reply: str, emit: Callable[[Event], None], record: bool = True
    ) -> TurnResult:
        result.reply = reply
        if record:
            self.history.append({"role": "assistant", "content": reply})
            emit({"type": "assistant_message", "text": reply})
        emit({"type": "state_change", "state": "idle"})
        self._trim_history()
        return result

    def _trim_history(self) -> None:
        if len(self.history) <= self.max_history:
            return
        cut = len(self.history) - self.max_history
        # Never start the history in the middle of a tool exchange.
        while cut < len(self.history) and self.history[cut]["role"] != "user":
            cut += 1
        self.history = self.history[cut:]

    def _handle_call(
        self, call: ToolCall, tainted: bool, result: TurnResult, emit: Callable[[Event], None]
    ) -> ToolResult:
        tool = self.registry.get(call.name)
        if tool is None:
            return ToolResult(
                False, f"Unknown tool '{call.name}'. Available: {', '.join(self.registry.names())}."
            )
        if call.parse_error:
            return ToolResult(False, f"The arguments were not valid JSON: {call.parse_error}")
        args, problem = tool.clean_args(call.arguments)
        if problem:
            return ToolResult(False, f"Invalid arguments for {tool.name}: {problem}.")

        verdict = self.permissions.evaluate(
            tool.name, tool.risk_for(args), tainted=tainted, skill=tool.skill
        )
        request = ApprovalRequest(
            call_id=call.id,
            tool=tool.name,
            args=args,
            risk=verdict.risk,
            decision=verdict.decision,
            preview=tool.preview(args),
            reason=verdict.reason,
        )
        approval = "auto"
        if verdict.decision == Decision.FORBID:
            return self._refused(
                request,
                "forbidden",
                "FORBIDDEN by the permission policy. Do not attempt this.",
                result,
                emit,
            )
        if verdict.decision in (Decision.CONFIRM, Decision.STEP_UP):
            emit(
                {
                    "type": "tool_call_proposed",
                    "call_id": call.id,
                    "tool": tool.name,
                    "args": args,
                    "risk": verdict.risk.label,
                    "decision": verdict.decision.value,
                    "preview": request.preview,
                    "reason": verdict.reason,
                }
            )
            if verdict.decision == Decision.CONFIRM:
                approved, approval = self.approver.confirm(request), "user_confirm"
            else:
                approved, approval = self.approver.step_up(request), "step_up"
            if not approved:
                return self._refused(
                    request,
                    "denied",
                    "DENIED by the user (or the required authentication did not succeed). "
                    "Do not retry this action in any form; tell the user it was not done.",
                    result,
                    emit,
                )

        emit(
            {
                "type": "tool_progress",
                "call_id": call.id,
                "tool": tool.name,
                "status": "started",
                "message": request.preview,
            }
        )
        try:
            outcome = tool.handler(**args)
        except Exception as exc:  # noqa: BLE001 - a tool must never crash the turn
            outcome = ToolResult(False, f"{tool.name} failed: {type(exc).__name__}")
        if tool.untrusted_output:
            outcome.untrusted = True
        emit(
            {
                "type": "tool_result",
                "call_id": call.id,
                "tool": tool.name,
                "ok": outcome.ok,
                "summary": outcome.content[:200],
            }
        )
        self._record(request, approval, outcome.ok, result)
        return outcome

    def _refused(
        self,
        request: ApprovalRequest,
        status: str,
        message: str,
        result: TurnResult,
        emit: Callable[[Event], None],
    ) -> ToolResult:
        emit(
            {
                "type": "tool_progress",
                "call_id": request.call_id,
                "tool": request.tool,
                "status": "denied",
                "message": request.reason,
            }
        )
        self._record(request, status, False, result)
        return ToolResult(False, message)

    def _record(
        self, request: ApprovalRequest, approval: str, ok: bool, result: TurnResult
    ) -> None:
        entry = {
            "tool": request.tool,
            "args": request.args,
            "risk": request.risk.label,
            "decision": request.decision.value,
            "approval": approval,
            "ok": ok,
        }
        result.tool_runs.append(entry)
        if self.log:
            self.log.record(**entry)

    def _offline_turn(
        self,
        text: str,
        error: AllProvidersFailed,
        result: TurnResult,
        emit: Callable[[Event], None],
    ) -> TurnResult:
        """No LLM is reachable: handle a basic command by rules, or explain honestly."""
        result.offline = True
        emit({"type": "state_change", "state": "offline"})
        # If tools already ran this turn, do not act again by rules.
        intent = None if result.tool_runs else offline.parse(text)
        if intent is not None and self.registry.get(intent.tool) is not None:
            call = ToolCall(id="offline_0", name=intent.tool, arguments=intent.args)
            outcome = self._handle_call(call, False, result, emit)
            if outcome.ok:
                reply = t("offline_prefix", self.language) + outcome.content
            elif result.tool_runs and result.tool_runs[-1]["approval"] in ("denied", "forbidden"):
                reply = t("denied", self.language)
            else:
                reply = t("offline_prefix", self.language) + outcome.content
        else:
            parts = [t("no_llm", self.language)]
            if error.reasons:
                parts.append("(" + "; ".join(error.reasons[:3]) + ")")
            else:
                parts.append(t("no_llm_setup", self.language))
            reply = " ".join(parts)
        # Drop a dangling assistant tool-call message, if the failure came mid-turn.
        while self.history and self.history[-1]["role"] != "user":
            self.history.pop()
        return self._finish(result, reply, emit)
