"""One app connection: its agent, its running turn and its pending approvals."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..agent import Agent, ApprovalRequest
from ..permissions import Risk
from ..strings import t
from .runtime import PROTOCOL_VERSION, CoreRuntime

Event = dict[str, Any]


class SessionApprover:
    """Waits for the user's answer to an approval card.

    The agent thread blocks in :meth:`confirm`; the connection calls
    :meth:`resolve` when ``approval_response`` arrives. No answer within the
    timeout, a closed connection or STOP all count as "no".
    """

    def __init__(self, timeout: float, on_step_up_blocked: Callable[[ApprovalRequest], None]):
        self.timeout = timeout
        self._on_step_up_blocked = on_step_up_blocked
        self._cond = threading.Condition()
        self._expected: set[str] = set()
        self._answers: dict[str, bool] = {}
        self._cancelled = False

    def expect(self, call_id: str) -> None:
        """An approval card for ``call_id`` is on its way to the app."""
        with self._cond:
            self._expected.add(call_id)

    def confirm(self, request: ApprovalRequest) -> bool:
        call_id = request.call_id
        with self._cond:
            self._expected.add(call_id)
            self._cond.wait_for(lambda: call_id in self._answers or self._cancelled, self.timeout)
            self._expected.discard(call_id)
            answer = self._answers.pop(call_id, False)
            return answer and not self._cancelled  # STOP wins over a late "yes"

    def step_up(self, request: ApprovalRequest) -> bool:
        # R3 needs two authentication factors. Until the security module
        # (Phase 3) exists there is no way to prove them, so the answer is no.
        self._on_step_up_blocked(request)
        return False

    def resolve(self, call_id: str, approved: bool) -> bool:
        """Record the user's answer. Returns False when nothing was waiting for it."""
        with self._cond:
            if call_id not in self._expected or call_id in self._answers:
                return False
            self._answers[call_id] = bool(approved)
            self._cond.notify_all()
            return True

    def cancel_all(self) -> None:
        """Answer "no" to everything that is waiting (STOP or disconnect)."""
        with self._cond:
            self._cancelled = True
            self._cond.notify_all()

    def reset(self) -> None:
        with self._cond:
            self._cancelled = False
            self._expected.clear()
            self._answers.clear()


class Session:
    def __init__(self, runtime: CoreRuntime, send: Callable[[Event], None]):
        self.runtime = runtime
        self._send = send  # thread-safe: called from the agent thread
        self.approver = SessionApprover(
            runtime.server_option("approval_timeout_seconds", 120.0), self._step_up_blocked
        )
        self._agent: Agent | None = None
        self._generation = -1
        self._turn = threading.Lock()
        self._proposals: dict[str, Event] = {}
        self._closed = False

    # ---- helpers -------------------------------------------------------

    def _language(self) -> str:
        return self._agent.language if self._agent else "hinglish"

    def _emit(self, event: Event) -> None:
        if event.get("type") == "tool_call_proposed":
            self._proposals[event["call_id"]] = event
            if event.get("decision") == "confirm":
                self.approver.expect(event["call_id"])
        self._send(event)

    def error(self, code: str, message: str) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "error", "code": code, "message": message})

    def _step_up_blocked(self, request: ApprovalRequest) -> None:
        self._send(
            {
                "v": PROTOCOL_VERSION,
                "type": "notice",
                "text": t("step_up_unavailable", self._language()),
            }
        )

    def _ensure_agent(self) -> Agent:
        """Build the agent, or rebuild it after a settings change, keeping the conversation."""
        if self._agent is None or self._generation != self.runtime.generation:
            generation = self.runtime.generation
            history = self._agent.history if self._agent else []
            trusted = self._agent.permissions.trusted_skills if self._agent else set()
            self._agent = self.runtime.build_agent(self.approver, self._emit)
            self._agent.history = history
            self._agent.permissions.trusted_skills |= trusted
            self._generation = generation
        return self._agent

    # ---- events from the app -------------------------------------------

    @property
    def busy(self) -> bool:
        return self._turn.locked()

    def try_begin_turn(self) -> bool:
        """Reserve the turn slot. Call from the connection before starting the worker."""
        return self._turn.acquire(blocking=False)

    def run_turn(self, text: str) -> None:
        """Run one user turn. Blocking: call in a worker thread after try_begin_turn."""
        try:
            self.approver.reset()
            self._proposals.clear()
            agent = self._ensure_agent()
            if self._closed:
                return
            agent.run_turn(text)
        except Exception as exc:  # noqa: BLE001 - never let a turn kill the connection
            self.error("internal", f"Something went wrong inside Rishu ({type(exc).__name__}).")
            self._send({"v": PROTOCOL_VERSION, "type": "state_change", "state": "idle"})
        finally:
            self._turn.release()

    def stop(self) -> None:
        self.approver.cancel_all()
        if self._agent is not None:
            self._agent.stop()

    def approval(self, call_id: str, approved: bool, always_allow: bool = False) -> None:
        proposal = self._proposals.get(call_id)
        if not self.approver.resolve(call_id, approved):
            self.error("no_such_approval", "That approval is no longer waiting.")
            return
        # "Always allow" marks the skill as trusted for this session. It never
        # applies to R3, and the permission engine honours it only in the
        # trusted_skills autonomy mode and never after untrusted content.
        if (
            approved
            and always_allow
            and proposal is not None
            and proposal.get("skill")
            and proposal.get("risk") != Risk.R3.label
            and self._agent is not None
        ):
            self._agent.permissions.trusted_skills.add(proposal["skill"])

    def new_conversation(self) -> None:
        if self._agent is not None and not self.busy:
            self._agent.reset()

    def close(self) -> None:
        self._closed = True
        self.stop()
