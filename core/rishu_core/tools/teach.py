"""Teach mode: the user shows Rishu a website task once, Rishu does it next time.

teach_start records the user's clicks and typing in Rishu's browser window;
teach_stop saves them as a skill. Every saved skill becomes its own tool
(``skill_<name>``) whose parameters are the values the user typed, so the
model can run it with new values. Running a skill is R2: one approval with
the full list of steps and values.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..browser import Browser, BrowserError, CdpError, format_outline
from ..permissions import Risk
from ..teach.replay import run_skill
from ..teach.skills import Skill, SkillStore, build_skill
from .registry import Tool, ToolResult

PREFIX = "skill_"


class TeachTools:
    def __init__(self, registry: Any, browser: Browser, store: SkillStore):
        self.registry = registry
        self.browser = browser
        self.store = store
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        self._recording: dict[str, Any] | None = None

    # ---- events for the app ------------------------------------------------------

    def state(self) -> dict[str, Any]:
        rec = self._recording
        steps: list[str] = []
        if rec is not None:
            draft = build_skill(rec["task"] or "draft", "", list(rec["raw"]), rec["start_url"])
            steps = [step.text() for step in draft.steps]
        return {
            "type": "teach_state",
            "recording": rec is not None,
            "task": rec["task"] if rec else "",
            "steps": steps[-20:],
            "skills": [
                {"name": s.name, "description": s.description, "steps": len(s.steps)}
                for s in self.store.load()
            ],
        }

    def _publish(self) -> None:
        event = self.state()
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:  # noqa: BLE001, S110 - a closed app must not break recording
                pass

    def _on_step(self, step: dict[str, Any]) -> None:
        with self._lock:
            if self._recording is None:
                return
            self._recording["raw"].append(step)
        self._publish()

    # ---- recording ------------------------------------------------------------------

    def start(self, task: str) -> ToolResult:
        if self._recording is not None:
            return ToolResult(
                False, "Already recording. Ask the user to finish showing the task first."
            )
        try:
            url = self.browser.start_recording(self._on_step)
        except (BrowserError, CdpError) as exc:
            return ToolResult(False, f"Could not start teach mode: {exc}")
        self._recording = {"task": task.strip()[:120], "raw": [], "start_url": url}
        self._publish()
        return ToolResult(
            True,
            "Teach mode is recording in Rishu's browser window. Tell the user warmly: please show the "
            "task once in that window (sign in yourself if asked); say 'bas, ho gaya' when finished. "
            "Do not use other browser tools until the user is done.",
        )

    def stop(self, name: str, description: str = "") -> ToolResult:
        rec = self._recording
        if rec is None:
            return ToolResult(False, "Teach mode is not recording.")
        self.browser.stop_recording()
        self._recording = None
        skill = build_skill(
            name or rec["task"], description or rec["task"], rec["raw"], rec["start_url"]
        )
        if not [s for s in skill.steps if s.action != "open"]:
            self._publish()
            return ToolResult(
                False, "Nothing was recorded in Rishu's browser window, so nothing was saved."
            )
        replaced = self.store.get(skill.name) is not None
        self.store.save(skill)
        self.sync()
        self._publish()
        params = ", ".join(f"{p.name} (e.g. {p.example})" for p in skill.params) or "none"
        steps = "\n".join(f"{i}. {s.text()}" for i, s in enumerate(skill.steps, start=1))
        return ToolResult(
            True,
            f"{'Updated' if replaced else 'Learned'} the skill '{skill.name}' ({len(skill.steps)} steps). "
            f"Values it asks for: {params}. Next time call the tool {PREFIX}{skill.slug}.\nSteps:\n{steps}",
            data={"skill": skill.name, "tool": PREFIX + skill.slug},
        )

    def cancel(self) -> ToolResult:
        if self._recording is None:
            return ToolResult(True, "Teach mode was not recording.")
        self.browser.stop_recording()
        self._recording = None
        self._publish()
        return ToolResult(True, "Stopped recording; nothing was saved.")

    # ---- skills ------------------------------------------------------------------

    def list(self) -> ToolResult:
        skills = self.store.load()
        if not skills:
            return ToolResult(
                True, "No taught skills yet. Offer teach mode: the user shows a task once."
            )
        lines = []
        for s in skills:
            params = ", ".join(p.name for p in s.params) or "no values"
            lines.append(
                f"- {s.name} ({PREFIX}{s.slug}): {s.description} — {len(s.steps)} steps, values: {params}, ran {s.runs}x"
            )
        return ToolResult(True, "Taught skills:\n" + "\n".join(lines))

    def delete(self, name: str) -> ToolResult:
        if not self.store.delete(name):
            return ToolResult(False, f"No taught skill called '{name}'.")
        self.sync()
        self._publish()
        return ToolResult(True, f"Forgot the skill '{name}'.")

    def run(self, skill_id: str, values: dict[str, Any]) -> ToolResult:
        skill = self.store.get(skill_id)
        if skill is None:
            return ToolResult(False, "That skill was deleted.")
        values = {k: str(v) for k, v in values.items() if v is not None}
        missing = [p.name for p in skill.params if not values.get(p.name, "").strip()]
        if missing:
            return ToolResult(False, f"Ask the user for: {', '.join(missing)}.")
        report = run_skill(self.browser, skill, values)
        if report.ok:
            self.store.count_run(skill)
            try:
                page = format_outline(self.browser.outline(), limit=40, text_chars=500)
            except (BrowserError, CdpError):
                page = ""
            return ToolResult(
                True,
                f"Did all {len(skill.steps)} steps of '{skill.name}'. Check the page below to confirm it worked.\n{page}",
                untrusted=True,
                source=report.url,
            )
        done = "; ".join(report.done[-5:]) or "none"
        return ToolResult(
            False,
            f"Stopped at step {report.failed_step} of {len(skill.steps)} ('{skill.name}'): {report.problem}. "
            f"Steps done: {done}. Ask the user to show you this task once more (teach_start, then "
            f"teach_stop with the same name '{skill.name}' replaces it).",
        )

    # ---- one tool per skill --------------------------------------------------------

    def _tool(self, skill: Skill) -> Tool:
        props = {
            p.name: {
                "type": "string",
                "description": f"{p.label or p.name} (taught example: {p.example})",
            }
            for p in skill.params
        }
        steps = "; ".join(s.text() for s in skill.steps[:8])

        def preview(args: dict[str, Any]) -> str:
            values = {k: str(v) for k, v in args.items()}
            lines = [f"Do the taught task '{skill.name}' in Rishu's browser:"]
            lines += [f"{i}. {s.text(values)}" for i, s in enumerate(skill.steps, start=1)]
            return "\n".join(lines)

        return Tool(
            name=PREFIX + skill.slug,
            description=(
                f"Taught by the user: {skill.description or skill.name}. Runs these steps in Rishu's "
                f"browser: {steps}. Call it directly when it fits; no need to read the page first."
            )[:900],
            parameters={
                "type": "object",
                "properties": props,
                "required": [p.name for p in skill.params],
            },
            risk=Risk.R2,
            handler=lambda **values: self.run(skill.id, values),
            untrusted_output=True,
            preview_fn=preview,
            skill=skill.slug,
        )

    def sync(self) -> None:
        for name in [n for n in self.registry.names() if n.startswith(PREFIX)]:
            self.registry.unregister(name)
        for skill in self.store.load():
            if self.registry.get(PREFIX + skill.slug) is None:
                self.registry.register(self._tool(skill))


def register(registry: Any, browser: Browser, store: SkillStore) -> TeachTools:
    from . import _obj

    teach = TeachTools(registry, browser, store)
    registry.register(
        Tool(
            name="teach_start",
            description=(
                "Teach mode: start recording while the user shows a website task once in Rishu's browser "
                "window (marks in the LMS, a form, a report). Use it when you do not know how to do a task "
                "instead of refusing: offer 'ek baar karke dikha dijiye, main seekh loongi'."
            ),
            parameters=_obj(
                {
                    "task": {
                        "type": "string",
                        "description": "What the user will show, in a few words",
                    }
                },
                ["task"],
            ),
            risk=Risk.R1,
            handler=teach.start,
            preview_fn=lambda a: (
                f"Start recording what you show in Rishu's browser: {a.get('task', '')}"
            ),
        )
    )
    registry.register(
        Tool(
            name="teach_stop",
            description=(
                "Teach mode: the user finished showing ('bas', 'ho gaya', 'done'). Save the recording as a "
                "skill. Reusing an existing name replaces that skill (re-teaching)."
            ),
            parameters=_obj(
                {
                    "name": {
                        "type": "string",
                        "description": "Short name, e.g. 'LMS assignment marks'",
                    },
                    "description": {
                        "type": "string",
                        "description": "One line: what the skill does",
                    },
                },
                ["name"],
            ),
            risk=Risk.R1,
            handler=teach.stop,
            preview_fn=lambda a: f"Save the taught task as '{a.get('name', '')}'",
        )
    )
    registry.register(
        Tool(
            name="teach_cancel",
            description="Teach mode: stop recording without saving.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=teach.cancel,
        )
    )
    registry.register(
        Tool(
            name="list_skills",
            description="List the tasks the user has taught Rishu (taught skills).",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=teach.list,
        )
    )
    registry.register(
        Tool(
            name="forget_skill",
            description="Delete a taught skill by its name.",
            parameters=_obj({"name": {"type": "string"}}, ["name"]),
            risk=Risk.R1,
            handler=teach.delete,
            preview_fn=lambda a: f"Forget the taught task '{a.get('name', '')}'",
        )
    )
    teach.sync()
    return teach
