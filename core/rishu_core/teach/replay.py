"""Run a taught skill again in Rishu's browser, with new values."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..browser import Browser, BrowserError, CdpError
from .skills import Skill, Step, fill


@dataclass
class RunReport:
    ok: bool
    done: list[str] = field(default_factory=list)
    failed_step: int | None = None  # 1-based
    problem: str = ""
    url: str = ""


def _target(step: Step, values: dict[str, str]) -> dict:
    target = dict(step.target or {})
    for key in ("name", "row"):
        if target.get(key):
            target[key] = fill(str(target[key]), values)
    return target


def run_skill(
    browser: Browser, skill: Skill, values: dict[str, str], find_timeout: float = 10
) -> RunReport:
    report = RunReport(ok=True)
    for index, step in enumerate(skill.steps, start=1):
        text = step.text(values)
        try:
            if step.action == "open":
                current = browser.run("() => location.href", timeout=5) if browser.url else ""
                if current != step.url:
                    browser.open(step.url)
            elif step.action == "press":
                browser.press(step.value or "Enter")
                browser.wait_ready(timeout=10)
            else:
                found = browser.find(_target(step, values), timeout=find_timeout)
                if found is None:
                    report.ok, report.failed_step = False, index
                    report.problem = f"could not find the control for: {text}"
                    break
                ref = found["ref"]
                if step.action == "click":
                    browser.click(ref)
                elif step.action == "type":
                    browser.type(ref, fill(step.value, values))
                elif step.action == "select":
                    browser.select(ref, fill(step.value, values))
        except (BrowserError, CdpError) as exc:
            report.ok, report.failed_step, report.problem = False, index, f"{text}: {exc}"
            break
        report.done.append(text)
    try:
        report.url = browser.run("() => location.href", timeout=5) or ""
    except (BrowserError, CdpError):
        pass
    return report
