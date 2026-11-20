"""Excel (.xlsx) and CSV files: find them, read them, fill a column by name.

"Aryan ke 8, Priya ke 9" or attendance counts read from a register photo go
into the right rows: Rishu matches each person by roll number or name
(spelling slips allowed, but never a guess between two people). The preview
shows every match before anything is written; the old file is kept as a
backup in Rishu's data folder.
"""

from __future__ import annotations

import csv
import difflib
import io
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from .registry import ToolResult

SHEET_TYPES = (".xlsx", ".xlsm", ".csv")
NAME_HINT = re.compile(r"name|naam|student|candidate", re.IGNORECASE)
ROLL_HINT = re.compile(r"roll|enrol|enroll|reg|admission|id\b|uid|sap", re.IGNORECASE)


def user_folders(home: Path | None = None) -> list[Path]:
    base = home or Path.home()
    names = [
        "Desktop",
        "Documents",
        "Downloads",
        "OneDrive",
        "OneDrive/Desktop",
        "OneDrive/Documents",
    ]
    return [base / n for n in names if (base / n).is_dir()]


def find_files(
    query: str, folders: list[Path] | None = None, limit: int = 15, max_depth: int = 4
) -> ToolResult:
    """Files whose name contains every word of the query, newest first."""
    words = [w for w in re.split(r"[\s_.-]+", query.lower()) if w]
    if not words:
        return ToolResult(False, "Say part of the file name.")
    found: list[tuple[float, Path]] = []
    for root in folders if folders is not None else user_folders():
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if len(Path(dirpath).parts) - root_depth >= max_depth:
                dirnames[:] = []
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith((".", "$")) and d not in ("node_modules", "AppData")
            ]
            for name in filenames:
                low = name.lower()
                if all(w in low for w in words):
                    path = Path(dirpath) / name
                    try:
                        found.append((path.stat().st_mtime, path))
                    except OSError:
                        continue
    if not found:
        return ToolResult(False, f'No file matching "{query}" in Desktop, Documents or Downloads.')
    found.sort(reverse=True)
    lines = [
        f"- {p} (changed {time.strftime('%d %b %Y %H:%M', time.localtime(t))})"
        for t, p in found[:limit]
    ]
    return ToolResult(
        True,
        "Files found (newest first):\n" + "\n".join(lines),
        data=[str(p) for _, p in found[:limit]],
    )


# ---- reading -------------------------------------------------------------------


class Table:
    """A sheet as rows of text, plus how to write cells back."""

    def __init__(self, path: Path, sheet: str = ""):
        self.path = path
        self.kind = path.suffix.lower()
        if self.kind not in SHEET_TYPES:
            raise ValueError("only .xlsx and .csv files are supported")
        self.sheet_name = sheet
        self._wb: Any = None
        self._ws: Any = None
        if self.kind == ".csv":
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig", errors="replace")
            try:
                self.dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            except csv.Error:
                self.dialect = csv.excel
            self.rows = [list(r) for r in csv.reader(io.StringIO(text), self.dialect)]
        else:
            import openpyxl

            self._wb = openpyxl.load_workbook(path)
            self._ws = (
                self._wb[sheet] if sheet and sheet in self._wb.sheetnames else self._wb.active
            )
            self.sheet_name = self._ws.title
            self.rows = [
                ["" if v is None else str(v).strip() for v in row]
                for row in self._ws.iter_rows(values_only=True)
            ]
        self.header_index = self._find_header()

    @property
    def sheets(self) -> list[str]:
        return list(self._wb.sheetnames) if self._wb is not None else []

    def _find_header(self) -> int:
        for i, row in enumerate(self.rows[:15]):
            filled = [c for c in row if c]
            if (
                len(filled) >= 2
                and sum(1 for c in filled if not re.fullmatch(r"[\d.,%-]+", c)) >= 2
            ):
                return i
        return 0

    @property
    def header(self) -> list[str]:
        return self.rows[self.header_index] if self.rows else []

    def data_rows(self) -> list[tuple[int, list[str]]]:
        return [
            (i, r) for i, r in enumerate(self.rows) if i > self.header_index and any(c for c in r)
        ]

    def column(self, wanted: str) -> int | None:
        low = wanted.strip().lower()
        for i, h in enumerate(self.header):
            if h.strip().lower() == low:
                return i
        for i, h in enumerate(self.header):
            if low and low in h.lower():
                return i
        return None

    def key_columns(self) -> tuple[int | None, int | None]:
        name = next((i for i, h in enumerate(self.header) if NAME_HINT.search(h)), None)
        roll = next(
            (i for i, h in enumerate(self.header) if ROLL_HINT.search(h) and i != name), None
        )
        return name, roll

    def set(self, row: int, col: int, value: str) -> None:
        if self.kind == ".csv":
            while len(self.rows[row]) <= col:
                self.rows[row].append("")
            self.rows[row][col] = value
        else:
            cell = self._ws.cell(row=row + 1, column=col + 1)
            number = value.strip()
            try:
                cell.value = (
                    int(number)
                    if re.fullmatch(r"-?\d+", number)
                    else float(number)
                    if re.fullmatch(r"-?\d+\.\d+", number)
                    else value
                )
            except ValueError:
                cell.value = value

    def add_column(self, title: str) -> int:
        col = len(self.header)
        self.set(self.header_index, col, title)
        if self.kind != ".csv":
            self.rows[self.header_index].append(title)
        return col

    def save(self) -> None:
        if self.kind == ".csv":
            encoding = "utf-8-sig" if self.path.read_bytes()[:3] == b"\xef\xbb\xbf" else "utf-8"
            # newline="": the csv writer chooses the line endings (no doubled \r on Windows).
            with self.path.open("w", encoding=encoding, newline="") as handle:
                csv.writer(handle, self.dialect).writerows(self.rows)
        else:
            self._wb.save(self.path)


def read_sheet(path: str, sheet: str = "", limit: int = 40) -> ToolResult:
    try:
        table = Table(Path(path).expanduser(), sheet)
    except FileNotFoundError:
        return ToolResult(False, f"File not found: {path}. Use find_files to look for it.")
    except (ValueError, OSError) as exc:
        return ToolResult(False, f"Could not open {path}: {exc}")
    except Exception as exc:  # noqa: BLE001 - a damaged workbook
        return ToolResult(False, f"Could not read {path}: {exc}")
    rows = table.data_rows()
    lines = [
        f"File: {table.path}"
        + (
            f" — sheet '{table.sheet_name}' (sheets: {', '.join(table.sheets)})"
            if table.sheets
            else ""
        )
    ]
    lines.append(
        "Columns: " + " | ".join(h or f"(col {i + 1})" for i, h in enumerate(table.header))
    )
    lines.append(f"{len(rows)} rows. First rows:")
    for _, row in rows[:limit]:
        lines.append(" | ".join(row))
    return ToolResult(True, "\n".join(lines), untrusted=True, source=str(table.path))


# ---- matching people to rows ---------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def match_row(who: str, table: Table, name_col: int | None, roll_col: int | None) -> list[int]:
    who_n = _norm(who)
    if not who_n:
        return []
    rows = table.data_rows()

    def cell(row: list[str], col: int | None) -> str:
        return row[col] if col is not None and col < len(row) else ""

    if any(ch.isdigit() for ch in who_n) and roll_col is not None:
        exact = [i for i, r in rows if _norm(cell(r, roll_col)) == who_n]
        if exact:
            return exact
        if who_n.isdigit() and len(who_n) <= 3:
            target = int(who_n)
            hits = []
            for i, r in rows:
                digits = re.search(r"(\d+)\D*$", cell(r, roll_col))
                if digits and int(digits.group(1)[-3:]) == target:
                    hits.append(i)
            return hits
        return [i for i, r in rows if _norm(cell(r, roll_col)).endswith(who_n)]
    if name_col is None:
        return []
    names = [(i, _norm(cell(r, name_col))) for i, r in rows]
    same = [i for i, n in names if n == who_n]
    if same:
        return same
    words = who_n.split()
    contains = [i for i, n in names if all(w in n.split() for w in words)]
    if contains:
        return contains
    # Spelling slips ("Aryaan" / "Aryan"): close to exactly one person.
    scored = sorted(
        (
            (
                max(
                    difflib.SequenceMatcher(None, who_n, n).ratio(),
                    max(
                        (difflib.SequenceMatcher(None, who_n, part).ratio() for part in n.split()),
                        default=0,
                    ),
                ),
                i,
            )
            for i, n in names
            if n
        ),
        reverse=True,
    )
    if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
        return [scored[0][1]]
    return [i for s, i in scored if s >= 0.85]


def plan_fill(
    path: str, column: str, values: dict[str, Any], sheet: str = "", match_column: str = ""
) -> dict[str, Any]:
    """Work out which row each value goes to, without writing anything."""
    table = Table(Path(path).expanduser(), sheet)
    name_col, roll_col = table.key_columns()
    if match_column:
        col = table.column(match_column)
        if col is None:
            raise ValueError(f"no column called '{match_column}'")
        if ROLL_HINT.search(table.header[col]):
            roll_col = col
        else:
            name_col = col
    target = table.column(column)
    plan: list[dict[str, Any]] = []
    problems: list[str] = []
    for who, value in values.items():
        hits = match_row(str(who), table, name_col, roll_col)
        if len(hits) == 1:
            row = table.rows[hits[0]]
            label = " / ".join(
                c
                for c in (
                    row[name_col] if name_col is not None and name_col < len(row) else "",
                    row[roll_col] if roll_col is not None and roll_col < len(row) else "",
                )
                if c
            )
            plan.append(
                {
                    "who": str(who),
                    "row": hits[0],
                    "label": label or f"row {hits[0] + 1}",
                    "value": str(value),
                }
            )
        elif not hits:
            problems.append(f'no row matches "{who}"')
        else:
            labels = ", ".join(
                table.rows[h][name_col] if name_col is not None else f"row {h + 1}"
                for h in hits[:4]
            )
            problems.append(f'"{who}" matches several rows: {labels}')
    return {
        "table": table,
        "column": target,
        "column_title": column,
        "plan": plan,
        "problems": problems,
    }


def preview_fill(args: dict[str, Any]) -> str:
    try:
        planned = plan_fill(
            args.get("path", ""),
            args.get("column", ""),
            args.get("values") or {},
            args.get("sheet", ""),
            args.get("match_column", ""),
        )
    except Exception as exc:  # noqa: BLE001 - the preview must never fail
        return f"Write {len(args.get('values') or {})} values into column '{args.get('column', '')}' of {args.get('path', '')} ({exc})"
    table = planned["table"]
    where = f"column '{planned['column_title']}'" + (
        "" if planned["column"] is not None else " (new column)"
    )
    lines = [
        f"Write into {where} of {table.path.name}"
        + (f" (sheet {table.sheet_name})" if table.sheets else "")
        + ":"
    ]
    lines += [f"• {p['label']} ← {p['value']}" for p in planned["plan"][:60]]
    if len(planned["plan"]) > 60:
        lines.append(f"… and {len(planned['plan']) - 60} more")
    if planned["problems"]:
        lines.append("Not found (nothing will be written): " + "; ".join(planned["problems"]))
    return "\n".join(lines)


def fill_sheet(
    path: str,
    column: str,
    values: dict[str, Any],
    sheet: str = "",
    match_column: str = "",
    backup_dir: Path | None = None,
) -> ToolResult:
    if not values:
        return ToolResult(False, "No values to write.")
    try:
        planned = plan_fill(path, column, values, sheet, match_column)
    except FileNotFoundError:
        return ToolResult(False, f"File not found: {path}. Use find_files to look for it.")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(False, f"Could not open {path}: {exc}")
    if planned["problems"]:
        return ToolResult(
            False, "Nothing was written. Please check: " + "; ".join(planned["problems"]) + "."
        )
    table: Table = planned["table"]
    col = planned["column"]
    if col is None:
        col = table.add_column(column)
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(table.path, backup_dir / f"{table.path.stem}-{stamp}{table.path.suffix}")
    for item in planned["plan"]:
        table.set(item["row"], col, item["value"])
    try:
        table.save()
    except PermissionError:
        return ToolResult(
            False, f"{table.path.name} is open in another program (Excel?). Close it and ask again."
        )
    done = ", ".join(f"{p['label']} = {p['value']}" for p in planned["plan"][:30])
    return ToolResult(
        True,
        f"Wrote {len(planned['plan'])} values into '{column}' of {table.path.name}: {done}. A backup of the old file is in Rishu's data folder.",
    )
