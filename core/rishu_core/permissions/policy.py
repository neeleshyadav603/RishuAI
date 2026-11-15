"""PROTECTED MODULE (spec §7): decides whether an action may run.

Every tool call passes through :class:`PermissionEngine`. Neither the LLM nor
any content it reads can change the outcome; only the user's settings and
``config/policy.yaml`` do.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any


class Risk(IntEnum):
    R0 = 0  # information only
    R1 = 1  # low: act, then say what was done
    R2 = 2  # medium: preview + explicit approval
    R3 = 3  # high: preview + step-up authentication (2 factors)

    @property
    def label(self) -> str:
        return f"R{int(self)}"


class Decision(StrEnum):
    ALLOW = "allow"
    ALLOW_NOTIFY = "allow_notify"
    CONFIRM = "confirm"
    STEP_UP = "step_up"
    FORBID = "forbid"


AUTONOMY_MODES = ("ask_always", "smart", "trusted_skills")


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    risk: Risk  # effective risk after the untrusted-content bump
    reason: str


class PermissionEngine:
    def __init__(
        self,
        policy: Mapping[str, Any],
        autonomy: str | None = None,
        trusted_skills: Iterable[str] = (),
    ):
        self._forbidden = frozenset(policy.get("forbidden_tools", ()))
        self._bump = max(0, int(policy.get("untrusted_bump", 1)))
        # R3 can never be automatic, whatever the policy file says.
        self._max_auto = min(int(policy.get("max_auto_risk", 2)), int(Risk.R2))
        mode = autonomy or policy.get("default_autonomy", "smart")
        if mode not in AUTONOMY_MODES:
            raise ValueError(f"unknown autonomy mode: {mode}")
        self.autonomy = mode
        self.trusted_skills = set(trusted_skills)

    def evaluate(
        self,
        tool: str,
        base_risk: Risk,
        *,
        tainted: bool = False,
        skill: str | None = None,
    ) -> Verdict:
        """Return what must happen before ``tool`` may run.

        ``tainted`` means untrusted content (a web page, a message, a file) was
        read earlier in this turn, so the request may not be the user's own.
        """
        if tool in self._forbidden:
            return Verdict(Decision.FORBID, Risk.R3, "forbidden by policy")

        risk = Risk(base_risk)
        reason = f"{risk.label} action"
        if tainted and risk >= Risk.R1:
            risk = Risk(min(int(Risk.R3), int(risk) + self._bump))
            reason = f"raised to {risk.label}: follows untrusted content"

        if risk == Risk.R3:
            return Verdict(Decision.STEP_UP, risk, reason)

        if (
            self.autonomy == "trusted_skills"
            and skill is not None
            and skill in self.trusted_skills
            and not tainted
            and Risk.R1 <= risk <= self._max_auto
        ):
            return Verdict(Decision.ALLOW_NOTIFY, risk, f"trusted skill '{skill}'")

        if risk == Risk.R2:
            return Verdict(Decision.CONFIRM, risk, reason)
        if risk == Risk.R1:
            if self.autonomy == "ask_always":
                return Verdict(Decision.CONFIRM, risk, "ask-always mode")
            return Verdict(Decision.ALLOW_NOTIFY, risk, reason)
        return Verdict(Decision.ALLOW, risk, reason)
