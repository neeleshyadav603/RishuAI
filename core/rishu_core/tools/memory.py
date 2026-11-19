"""Things the user asked Rishu to remember. Kept on this computer only.

Facts are given to the model in the system prompt, so Rishu can use them in
any later conversation. The user can list and forget them at any time.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .registry import ToolResult

MAX_FACTS = 200
PROMPT_FACTS = 40


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return (
            [f for f in data if isinstance(f, dict) and isinstance(f.get("text"), str)]
            if isinstance(data, list)
            else []
        )

    def _save(self, facts: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temp, self.path)

    def add(self, text: str) -> dict[str, Any]:
        text = " ".join(text.split())[:300]
        with self._lock:
            facts = [f for f in self.load() if f["text"].lower() != text.lower()]
            fact = {"id": uuid.uuid4().hex[:6], "text": text, "ts": time.time()}
            facts.append(fact)
            self._save(facts[-MAX_FACTS:])
        return fact

    def forget(self, query: str) -> list[str]:
        q = query.strip().lower()
        with self._lock:
            facts = self.load()
            gone = [f for f in facts if q and (f["id"] == q or q in f["text"].lower())]
            if gone:
                self._save([f for f in facts if f not in gone])
        return [f["text"] for f in gone]

    def prompt_block(self) -> str:
        facts = self.load()[-PROMPT_FACTS:]
        if not facts:
            return ""
        lines = "\n".join(f"- {f['text']}" for f in facts)
        return (
            "What the user asked you to remember (use it when relevant; never invent more):\n"
            + lines
        )


def remember(store: MemoryStore, fact: str) -> ToolResult:
    if not fact.strip():
        return ToolResult(False, "What should I remember?")
    saved = store.add(fact)
    return ToolResult(True, f"I will remember: {saved['text']}", data=saved)


def forget(store: MemoryStore, about: str) -> ToolResult:
    gone = store.forget(about)
    if not gone:
        return ToolResult(False, "I don't have anything like that saved.")
    return ToolResult(True, "Forgot: " + "; ".join(gone))


def list_memories(store: MemoryStore) -> ToolResult:
    facts = store.load()
    if not facts:
        return ToolResult(True, "I have not saved anything about you yet.", data=[])
    return ToolResult(True, "\n".join(f"- {f['text']}" for f in facts), data=facts)
