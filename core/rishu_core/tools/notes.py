"""Quick notes in the user's data folder (moves to the encrypted store in Phase 3)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .registry import ToolResult


class NotesStore:
    def __init__(self, path: Path):
        self.path = path

    def add(self, text: str) -> dict:
        note = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "text": text.strip()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(note, ensure_ascii=False) + "\n")
        return note

    def list(self, limit: int = 10) -> list[dict]:
        if not self.path.exists():
            return []
        notes = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                notes.append(json.loads(line))
            except ValueError:
                continue
        return notes[-limit:]


def add_note(store: NotesStore, text: str) -> ToolResult:
    if not text.strip():
        return ToolResult(False, "The note is empty.")
    note = store.add(text)
    return ToolResult(True, f"Note saved: {note['text']}", data=note)


def list_notes(store: NotesStore, limit: int = 10) -> ToolResult:
    notes = store.list(max(1, min(int(limit), 50)))
    if not notes:
        return ToolResult(True, "There are no notes yet.", data=[])
    lines = [
        f"- {time.strftime('%d %b %Y %H:%M', time.localtime(n['ts']))}: {n['text']}" for n in notes
    ]
    return ToolResult(True, "\n".join(lines), data=notes)
