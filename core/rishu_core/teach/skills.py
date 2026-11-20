"""Taught skills: what the user showed Rishu once, saved as steps with parameters.

A skill is a short list of browser steps (open, click, type, select, press).
Values the user typed become parameters, so the skill runs again with new
values ("Priya ke 8 marks"). Skills are stored encrypted in the data folder.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..security.vault import Vault, default_vault

PARAM = re.compile(r"\{\{(\w+)\}\}")
MAX_STEPS = 60


def slug(text: str, fallback: str = "value") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (cleaned[:30].strip("_") or fallback) if cleaned else fallback


@dataclass
class Step:
    action: str  # open | click | type | select | press
    target: dict[str, Any] | None = None
    value: str = ""
    url: str = ""

    def text(self, values: dict[str, str] | None = None) -> str:
        """Plain description, with parameter values filled in when given."""
        value = fill(self.value, values) if values else self.value
        label = ""
        if self.target:
            name = (
                fill(self.target.get("name") or "", values)
                if values
                else self.target.get("name") or ""
            )
            row = (
                fill(self.target.get("row") or "", values)
                if values
                else self.target.get("row") or ""
            )
            label = f'"{name}"' if name else "the control"
            if row:
                label += f" (row: {row[:50]})"
        if self.action == "open":
            return f"Open {self.url}"
        if self.action == "click":
            return f"Click {label}"
        if self.action == "type":
            return f'Type "{value}" into {label}'
        if self.action == "select":
            return f'Choose "{value}" in {label}'
        if self.action == "press":
            return f"Press {value or 'Enter'}"
        return self.action


@dataclass
class Param:
    name: str
    example: str
    label: str = ""


@dataclass
class Skill:
    id: str
    name: str
    description: str
    steps: list[Step]
    params: list[Param] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    runs: int = 0

    @property
    def slug(self) -> str:
        return slug(self.name, "skill")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            steps=[Step(**s) for s in data.get("steps", [])],
            params=[Param(**p) for p in data.get("params", [])],
            created=float(data.get("created", time.time())),
            updated=float(data.get("updated", time.time())),
            runs=int(data.get("runs", 0)),
        )


def fill(text: str, values: dict[str, str] | None) -> str:
    if not values:
        return text
    return PARAM.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)


def build_skill(
    name: str, description: str, raw: list[dict[str, Any]], start_url: str = ""
) -> Skill:
    """Turn the recorded events into steps and parameters."""
    steps: list[Step] = []
    if start_url.startswith(("http://", "https://")):
        steps.append(Step("open", url=start_url))
    last_action_at = 0.0
    for event in raw:
        kind = event.get("kind")
        at = float(event.get("at") or 0)
        if kind == "navigated":
            url = str(event.get("url", ""))
            # A page change right after a click or Enter is the result of that step.
            if not url.startswith(("http://", "https://")) or (at and at - last_action_at < 3000):
                continue
            if steps and steps[-1].action == "open":
                steps[-1] = Step("open", url=url)
            else:
                steps.append(Step("open", url=url))
            continue
        target = event.get("target") if isinstance(event.get("target"), dict) else None
        if kind in ("click", "press"):
            last_action_at = at or last_action_at
        if kind == "type" and steps and steps[-1].action == "type" and steps[-1].target == target:
            steps[-1].value = str(event.get("value", ""))  # the final text of the same field
            continue
        if kind == "type" and any(
            s.action == "type" and s.target == target and s.value == str(event.get("value", ""))
            for s in steps[-3:]
        ):
            continue  # the same text again (Enter, then the field lost focus)
        if kind == "click":
            steps.append(Step("click", target=target))
        elif kind == "type":
            steps.append(Step("type", target=target, value=str(event.get("value", ""))))
        elif kind == "select":
            steps.append(Step("select", target=target, value=str(event.get("value", ""))))
        elif kind == "press":
            steps.append(Step("press", target=target, value=str(event.get("key", "Enter"))))
    steps = steps[:MAX_STEPS]

    # Typed and chosen values become parameters; rows that show such a value
    # (a student's name typed into the search box) follow the parameter.
    params: list[Param] = []
    used: set[str] = set()
    for step in steps:
        if step.action not in ("type", "select") or not step.value.strip():
            continue
        label = (step.target or {}).get("name", "") or "value"
        base = slug(label)
        pname, n = base, 2
        while pname in used:
            pname, n = f"{base}_{n}", n + 1
        used.add(pname)
        example = step.value
        params.append(Param(pname, example, label))
        step.value = "{{" + pname + "}}"
        needle = example.strip().lower()
        if len(needle) >= 3:
            for later in steps:
                row = (later.target or {}).get("row") or ""
                if later.target and needle in row.lower():
                    later.target = {**later.target, "row": "{{" + pname + "}}"}
    return Skill(uuid.uuid4().hex[:8], name.strip()[:60], description.strip()[:300], steps, params)


class SkillStore:
    def __init__(self, path: Path, vault: Vault | None = None):
        self.path = path
        self.vault = vault or default_vault()
        self._lock = threading.Lock()

    def load(self) -> list[Skill]:
        try:
            data = json.loads(self.vault.read_text(self.path) or "[]")
        except ValueError:
            return []
        skills = []
        for item in data if isinstance(data, list) else []:
            try:
                skills.append(Skill.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
        return skills

    def _save(self, skills: list[Skill]) -> None:
        self.vault.write_text(
            self.path, json.dumps([s.to_dict() for s in skills], ensure_ascii=False, indent=1)
        )

    def get(self, name: str) -> Skill | None:
        key = slug(name, "skill")
        return next((s for s in self.load() if s.slug == key or s.id == name), None)

    def save(self, skill: Skill) -> Skill:
        """Add, or replace the skill with the same name (teaching it again)."""
        with self._lock:
            skills = [s for s in self.load() if s.slug != skill.slug]
            old = next((s for s in self.load() if s.slug == skill.slug), None)
            if old is not None:
                skill.id, skill.created, skill.runs = old.id, old.created, old.runs
            skill.updated = time.time()
            skills.append(skill)
            self._save(skills)
            return skill

    def delete(self, name: str) -> bool:
        with self._lock:
            skills = self.load()
            kept = [s for s in skills if s.slug != slug(name, "skill") and s.id != name]
            if len(kept) == len(skills):
                return False
            self._save(kept)
            return True

    def count_run(self, skill: Skill) -> None:
        with self._lock:
            skills = self.load()
            for s in skills:
                if s.id == skill.id:
                    s.runs += 1
            self._save(skills)
