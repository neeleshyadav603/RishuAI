"""Append-only record of every action Rishu takes (spec §6).

Plain JSON lines for now; Phase 3 moves this into the encrypted store.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ActivityLog:
    def __init__(self, path: Path):
        self.path = path

    def record(self, **fields: Any) -> dict[str, Any]:
        entry = {"ts": time.time(), **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
        return entries
