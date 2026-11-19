"""Quick notes in the user's data folder, encrypted on Windows (DPAPI)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from ..security.vault import Vault, default_vault
from .registry import ToolResult


class NotesStore:
    def __init__(self, path: Path, vault: Vault | None = None):
        self.path = path
        self.vault = vault or default_vault()
        self._lock = threading.Lock()

    def _all(self) -> list[dict]:
        notes = []
        for line in (self.vault.read_text(self.path) or "").splitlines():
            try:
                note = json.loads(line)
            except ValueError:
                continue
            if isinstance(note, dict):
                notes.append(note)
        return notes

    def add(self, text: str) -> dict:
        note = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "text": text.strip()}
        with self._lock:
            notes = self._all() + [note]
            self.vault.write_text(
                self.path, "".join(json.dumps(n, ensure_ascii=False) + "\n" for n in notes)
            )
        return note

    def list(self, limit: int = 10) -> list[dict]:
        return self._all()[-limit:]


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
