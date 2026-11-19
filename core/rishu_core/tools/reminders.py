"""Reminders and timers: Rishu speaks them aloud when they are due."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..security.vault import Vault, default_vault
from .registry import ToolResult

_CLOCK = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


class ReminderStore:
    def __init__(
        self, path: Path, clock: Callable[[], float] = time.time, vault: Vault | None = None
    ):
        self.path = path
        self._clock = clock
        self.vault = vault or default_vault()
        self._lock = threading.Lock()

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.vault.read_text(self.path) or "[]")
        except ValueError:
            return []
        return (
            [r for r in data if isinstance(r, dict) and "due" in r and "text" in r]
            if isinstance(data, list)
            else []
        )

    def _save(self, items: list[dict[str, Any]]) -> None:
        self.vault.write_text(self.path, json.dumps(items, ensure_ascii=False, indent=1))

    def add(self, text: str, due: float) -> dict[str, Any]:
        item = {
            "id": uuid.uuid4().hex[:6],
            "text": text.strip(),
            "due": due,
            "created": self._clock(),
        }
        with self._lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._load(), key=lambda r: r["due"])

    def cancel(self, ident: str) -> bool:
        with self._lock:
            items = self._load()
            kept = [r for r in items if r.get("id") != ident]
            self._save(kept)
            return len(kept) != len(items)

    def pop_due(self) -> list[dict[str, Any]]:
        now = self._clock()
        with self._lock:
            items = self._load()
            due = [r for r in items if r["due"] <= now]
            if due:
                self._save([r for r in items if r["due"] > now])
            return due


def parse_due(minutes: float | None, at: str | None, now: datetime) -> datetime | None:
    if minutes is not None:
        if not 0 < minutes <= 60 * 24 * 7:
            return None
        return now + timedelta(minutes=minutes)
    if at:
        match = _CLOCK.match(at)
        if not match:
            return None
        hour, minute, ampm = (
            int(match.group(1)),
            int(match.group(2) or 0),
            (match.group(3) or "").lower(),
        )
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            return None
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due
    return None


def set_reminder(
    store: ReminderStore,
    text: str,
    minutes: float | None = None,
    at: str | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> ToolResult:
    if not text.strip():
        return ToolResult(False, "What should I remind you about?")
    current = now()
    due = parse_due(minutes, at, current)
    if due is None:
        return ToolResult(
            False, "Give the time as minutes from now (up to 7 days) or a clock time like 17:30."
        )
    item = store.add(text, due.timestamp())
    when = due.strftime("%I:%M %p") + (
        "" if due.date() == current.date() else due.strftime(", %d %b")
    )
    return ToolResult(True, f"Reminder set for {when}: {item['text']}", data=item)


def list_reminders(store: ReminderStore) -> ToolResult:
    items = store.pending()
    if not items:
        return ToolResult(True, "No reminders are set.", data=[])
    lines = [
        f"- {datetime.fromtimestamp(r['due']).strftime('%d %b %I:%M %p')}: {r['text']} (id {r['id']})"
        for r in items
    ]
    return ToolResult(True, "\n".join(lines), data=items)


def cancel_reminder(store: ReminderStore, ident: str) -> ToolResult:
    if store.cancel(ident.strip()):
        return ToolResult(True, "Reminder cancelled.")
    return ToolResult(False, "No reminder with that id.")
