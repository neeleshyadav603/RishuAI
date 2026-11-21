"""Teacher mode: weekly timetable with a reminder before each lecture, and
class material as real files (Word notes and question papers, Excel sheets).

The timetable is stored encrypted in the data folder. Files are written to
Documents/Rishu so the user finds them easily.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..security.vault import Vault, default_vault
from .registry import ToolResult

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAY_ALIASES = {
    "mon": 0, "somvar": 0, "somwar": 0, "tue": 1, "tues": 1, "mangalvar": 1, "mangalwar": 1,
    "wed": 2, "budhvar": 2, "budhwar": 2, "thu": 3, "thur": 3, "thurs": 3, "guruvar": 3, "guruwar": 3,
    "brihaspativar": 3, "fri": 4, "shukravar": 4, "shukrawar": 4, "sat": 5, "shanivar": 5, "shaniwar": 5,
    "sun": 6, "ravivar": 6, "raviwar": 6, "itvar": 6,
}  # fmt: skip
_TIME = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


def day_index(day: str) -> int | None:
    low = day.strip().lower()
    if low in DAYS:
        return DAYS.index(low)
    return _DAY_ALIASES.get(low)


def parse_clock(text: str) -> str | None:
    """'9', '9:30', '2 pm', '14.10' -> 'HH:MM' (24 h). Class hours 1-7 without am/pm mean afternoon."""
    match = _TIME.match(str(text))
    if not match:
        return None
    hour, minute, half = (
        int(match.group(1)),
        int(match.group(2) or 0),
        (match.group(3) or "").lower(),
    )
    if half == "pm" and hour < 12:
        hour += 12
    elif half == "am" and hour == 12:
        hour = 0
    elif not half and 1 <= hour <= 7:
        hour += 12  # "2 baje ki class" is in the afternoon
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


class Timetable:
    def __init__(
        self, path: Path, vault: Vault | None = None, now: Callable[[], datetime] = datetime.now
    ):
        self.path = path
        self.vault = vault or default_vault()
        self._now = now
        self._lock = threading.Lock()
        self._announced: set[str] = set()

    def load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.vault.read_text(self.path) or "[]")
        except ValueError:
            return []
        return (
            [e for e in data if isinstance(e, dict) and "day" in e and "start" in e]
            if isinstance(data, list)
            else []
        )

    def _save(self, entries: list[dict[str, Any]]) -> None:
        entries.sort(key=lambda e: (e["day"], e["start"]))
        self.vault.write_text(self.path, json.dumps(entries, ensure_ascii=False, indent=1))

    def add(
        self, entries: list[dict[str, Any]], replace: bool = False
    ) -> tuple[list[dict[str, Any]], list[str]]:
        added, problems = [], []
        for raw in entries:
            day = day_index(str(raw.get("day", "")))
            start = parse_clock(str(raw.get("start", "")))
            end = parse_clock(str(raw.get("end", ""))) if raw.get("end") else None
            subject = " ".join(str(raw.get("subject", "")).split())[:80]
            if day is None or start is None or not subject:
                problems.append(f"skipped {raw}: needs day, start time and subject")
                continue
            added.append(
                {
                    "day": day,
                    "start": start,
                    "end": end or "",
                    "subject": subject,
                    "group": " ".join(str(raw.get("group", "")).split())[:60],
                    "room": " ".join(str(raw.get("room", "")).split())[:30],
                }
            )
        with self._lock:
            current = [] if replace else self.load()
            keys = {(e["day"], e["start"]) for e in added}
            current = [e for e in current if (e["day"], e["start"]) not in keys] + added
            self._save(current)
        return added, problems

    def remove(self, day: str, start: str = "") -> int:
        index = day_index(day)
        clock = parse_clock(start) if start else None
        with self._lock:
            entries = self.load()
            kept = [
                e
                for e in entries
                if not (e["day"] == index and (clock is None or e["start"] == clock))
            ]
            self._save(kept)
            return len(entries) - len(kept)

    def on(self, day: int) -> list[dict[str, Any]]:
        return [e for e in self.load() if e["day"] == day]

    def due_soon(self, minutes_before: int) -> list[dict[str, Any]]:
        """Lectures that start in about ``minutes_before`` minutes, each announced once."""
        now = self._now()
        due = []
        for entry in self.on(now.weekday()):
            hour, minute = map(int, entry["start"].split(":"))
            starts = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = f"{now.date()}-{entry['start']}-{entry['subject']}"
            if key in self._announced:
                continue
            if timedelta(0) <= starts - now <= timedelta(minutes=minutes_before):
                self._announced.add(key)
                due.append(
                    {**entry, "in_minutes": max(0, round((starts - now).total_seconds() / 60))}
                )
        return due


def describe(entry: dict[str, Any]) -> str:
    when = entry["start"] + (f"-{entry['end']}" if entry.get("end") else "")
    extra = ", ".join(
        x for x in (entry.get("group"), f"room {entry['room']}" if entry.get("room") else "") if x
    )
    return f"{DAYS[entry['day']].title()} {when}: {entry['subject']}" + (
        f" ({extra})" if extra else ""
    )


def show(table: Timetable, day: str = "", now: Callable[[], datetime] = datetime.now) -> ToolResult:
    low = day.strip().lower()
    today = now().weekday()
    if low in ("", "today", "aaj"):
        index: int | None = today
    elif low in ("tomorrow", "kal"):
        index = (today + 1) % 7
    elif low in ("week", "all", "poora", "hafta"):
        index = None
    else:
        index = day_index(low)
        if index is None:
            return ToolResult(False, f"Which day is '{day}'?")
    entries = table.load() if index is None else table.on(index)
    if not entries:
        if not table.load():
            return ToolResult(
                True,
                "No timetable saved yet. Ask the user for their weekly classes (day, time, subject, class).",
            )
        return ToolResult(
            True, f"No classes on {DAYS[index].title() if index is not None else 'any day'}."
        )
    current = now().strftime("%H:%M")
    lines = []
    for entry in entries:
        mark = (
            " ← next"
            if index == today
            and entry["start"] >= current
            and all(not (e["start"] >= current and e["start"] < entry["start"]) for e in entries)
            else ""
        )
        lines.append("- " + describe(entry) + mark)
    return ToolResult(True, "\n".join(lines))


# ---- files -----------------------------------------------------------------------


def output_folder(home: Path | None = None) -> Path:
    base = (home or Path.home()) / "Documents"
    folder = (base if base.is_dir() else (home or Path.home())) / "Rishu"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_name(name: str, suffix: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", name).strip().strip(".")[:80] or "Rishu"
    return stem + suffix


def _unique(folder: Path, name: str) -> Path:
    path = folder / name
    n = 2
    while path.exists():
        path = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return path


def make_document(
    title: str, content: str, file_name: str = "", folder: Path | None = None
) -> ToolResult:
    """A Word file from simple markdown: # headings, - bullets, 1. numbers, **bold**, tables with |."""
    from docx import Document
    from docx.shared import Pt

    folder = folder or output_folder()
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    document.add_heading(title.strip()[:200] or "Rishu", level=0)
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        rows = [
            r
            for r in table_rows
            if not all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in r if c.strip())
        ]
        table_rows.clear()
        if not rows:
            return
        width = max(len(r) for r in rows)
        table = document.add_table(rows=len(rows), cols=width)
        table.style = "Table Grid"
        for i, row in enumerate(rows):
            for j in range(width):
                cell = table.cell(i, j)
                cell.text = row[j].strip() if j < len(row) else ""
                if i == 0:
                    for run in cell.paragraphs[0].runs:
                        run.bold = True

    def add_runs(paragraph: Any, text: str) -> None:
        for k, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
            if part:
                paragraph.add_run(part).bold = k % 2 == 1

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows.append(stripped.strip("|").split("|"))
            continue
        flush_table()
        if not stripped:
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if heading:
            document.add_heading(heading.group(2), level=len(heading.group(1)))
        elif re.match(r"^[-*•]\s+", stripped):
            add_runs(
                document.add_paragraph(style="List Bullet"), re.sub(r"^[-*•]\s+", "", stripped)
            )
        elif re.match(r"^\d+[.)]\s+", stripped):
            add_runs(
                document.add_paragraph(style="List Number"), re.sub(r"^\d+[.)]\s+", "", stripped)
            )
        else:
            add_runs(document.add_paragraph(), stripped)
    flush_table()
    path = _unique(folder, _safe_name(file_name or title, ".docx"))
    document.save(path)
    return ToolResult(
        True, f"Saved the Word file {path}. Offer to open it.", data={"path": str(path)}
    )


def make_spreadsheet(
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    file_name: str = "",
    folder: Path | None = None,
) -> ToolResult:
    """An Excel file with a bold header row, sized columns and numbers kept as numbers."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    if not columns:
        return ToolResult(False, "The sheet needs column titles.")
    folder = folder or output_folder()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]:*?/\\]", " ", title)[:31] or "Sheet1"
    ws.append([str(c) for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4B3FCF")
    for row in rows:
        values = []
        for value in list(row)[: len(columns)]:
            text = str(value).strip() if value is not None else ""
            if re.fullmatch(r"-?\d+", text):
                values.append(int(text))
            elif re.fullmatch(r"-?\d+\.\d+", text):
                values.append(float(text))
            else:
                values.append(text)
        ws.append(values)
    for i, column in enumerate(columns, start=1):
        width = max([len(str(column))] + [len(str(r[i - 1])) for r in rows if len(r) >= i])
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(60, width + 3)
    ws.freeze_panes = "A2"
    path = _unique(folder, _safe_name(file_name or title, ".xlsx"))
    wb.save(path)
    return ToolResult(
        True,
        f"Saved the Excel file {path} ({len(rows)} rows). Offer to open it.",
        data={"path": str(path)},
    )
