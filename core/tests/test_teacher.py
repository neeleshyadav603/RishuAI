"""Teacher mode: timetable, lecture reminders, Word and Excel files."""

from datetime import datetime

import docx
import openpyxl

from rishu_core.security.vault import Vault
from rishu_core.tools import teacher


class Clock:
    def __init__(self, when):
        self.when = when

    def __call__(self):
        return self.when


def make_table(tmp_path, clock):
    return teacher.Timetable(tmp_path / "timetable.json", vault=Vault(platform="linux"), now=clock)


def test_clock_and_day_parsing():
    assert teacher.parse_clock("9:30") == "09:30" and teacher.parse_clock("2") == "14:00"
    assert teacher.parse_clock("2 pm") == "14:00" and teacher.parse_clock("11.15") == "11:15"
    assert teacher.parse_clock("25") is None and teacher.parse_clock("abc") is None
    assert (
        teacher.day_index("Somvar") == 0
        and teacher.day_index("friday") == 4
        and teacher.day_index("x") is None
    )


def test_timetable_today_tomorrow_and_reminders(tmp_path):
    clock = Clock(datetime(2026, 11, 23, 9, 20))  # a Monday
    table = make_table(tmp_path, clock)
    added, problems = table.add(
        [
            {
                "day": "monday",
                "start": "9:30",
                "end": "10:30",
                "subject": "DAA",
                "group": "CSE 5 A",
                "room": "204",
            },
            {"day": "monday", "start": "2", "subject": "Software Engineering", "group": "AI&DS 5"},
            {"day": "tuesday", "start": "10", "subject": "COI"},
            {"day": "funday", "start": "10", "subject": "x"},
        ]
    )
    assert len(added) == 3 and problems
    today = teacher.show(table, "aaj", clock)
    assert (
        "09:30-10:30: DAA (CSE 5 A, room 204) ← next" in today.content and "14:00" in today.content
    )
    assert "COI" in teacher.show(table, "kal", clock).content
    assert "Tuesday" in teacher.show(table, "week", clock).content
    due = table.due_soon(10)
    assert [d["subject"] for d in due] == ["DAA"] and due[0]["in_minutes"] == 10
    assert table.due_soon(10) == []  # said once
    assert table.remove("monday", "2") == 1
    assert "Software" not in teacher.show(table, "today", clock).content


def test_lecture_reminder_is_spoken_in_the_open_window(settings, registry, tmp_path):
    from fastapi.testclient import TestClient
    from test_api import AUTH, make_runtime, read_until

    from rishu_core.api import create_app

    clock = Clock(datetime(2026, 11, 23, 13, 52))
    registry.timetable = make_table(tmp_path, clock)
    registry.timetable.add(
        [{"day": "monday", "start": "2 pm", "subject": "DAA", "group": "CSE 5 B"}]
    )
    runtime = make_runtime(settings, registry, tmp_path, script=[])
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        assert runtime.check_lectures() == 1
        event = read_until(ws, "reminder")[-1]
    assert event["text"] == "8 minute mein DAA ki class hai (CSE 5 B)"


def test_word_and_excel_files(tmp_path):
    content = """# Unit 1: Sorting
Sorting puts items in order.
- **Bubble sort**: swaps neighbours
1. Write the algorithm
| Algorithm | Best | Worst |
|---|---|---|
| Bubble | O(n) | O(n^2) |
"""
    result = teacher.make_document("DAA notes", content, "DAA Unit 1", folder=tmp_path)
    assert result.ok
    doc = docx.Document(result.data["path"])
    texts = [p.text for p in doc.paragraphs]
    assert "Unit 1: Sorting" in texts and any("Bubble sort" in t for t in texts)
    assert doc.tables[0].cell(1, 2).text == "O(n^2)"
    again = teacher.make_document("DAA notes", "x", "DAA Unit 1", folder=tmp_path)
    assert again.data["path"].endswith("DAA Unit 1 (2).docx")  # never overwrites
    sheet = teacher.make_spreadsheet(
        "Result DAA",
        ["Roll", "Name", "Marks"],
        [["22CSE005", "Aryan", "18"], ["22CSE012", "Priya", "19.5"]],
        folder=tmp_path,
    )
    ws = openpyxl.load_workbook(sheet.data["path"]).active
    assert (
        ws["A1"].value == "Roll"
        and ws["C2"].value == 18
        and ws["C3"].value == 19.5
        and ws.freeze_panes == "A2"
    )


def test_open_file_refuses_programs(registry, tmp_path, opened_urls):
    (tmp_path / "notes.docx").write_text("x")
    (tmp_path / "setup.exe").write_text("x")
    tool = registry.get("open_file")
    assert tool.handler(path=str(tmp_path / "notes.docx")).ok and opened_urls[-1].endswith(
        "notes.docx"
    )
    assert not tool.handler(path=str(tmp_path / "setup.exe")).ok
