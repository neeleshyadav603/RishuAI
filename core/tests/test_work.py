"""Everyday work tools: documents, tidy folders, dictation, deadlines, invoices, briefing, meetings."""

import os
import time
import zipfile
from contextlib import contextmanager
from datetime import date, datetime

import pytest

from rishu_core.permissions import Risk
from rishu_core.tools import work


def run(registry, tool, **args):
    return registry.get(tool).handler(**args)


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF with real text (no PDF library needed to make it)."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


# ---- read_document -----------------------------------------------------------------


def test_reads_pdf_word_excel_powerpoint_and_text(tmp_path):
    from docx import Document
    from openpyxl import Workbook

    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(tiny_pdf("Unit 3 Greedy Algorithms"))
    result = work.read_document(str(pdf))
    assert result.ok and result.untrusted and "Greedy Algorithms" in result.content
    assert "pages 1-1 of 1" in result.content

    doc = Document()
    doc.add_paragraph("Assignment 2: Software testing")
    doc.add_table(rows=1, cols=2).rows[0].cells[0].text = "Marks"
    doc.save(tmp_path / "a.docx")
    text = work.read_document(str(tmp_path / "a.docx")).content
    assert "Software testing" in text and "Marks" in text

    book = Workbook()
    book.active.append(["Roll", "Marks"])
    book.active.append(["R1", 18])
    book.save(tmp_path / "m.xlsx")
    assert "R1 | 18" in work.read_document(str(tmp_path / "m.xlsx")).content

    with zipfile.ZipFile(tmp_path / "s.pptx", "w") as z:
        z.writestr("ppt/slides/slide2.xml", "<p><a:t>Second slide</a:t></p>")
        z.writestr("ppt/slides/slide1.xml", "<p><a:t>Intro &amp; aims</a:t></p>")
    slides = work.read_document(str(tmp_path / "s.pptx")).content
    assert slides.index("Intro & aims") < slides.index("Second slide")

    (tmp_path / "t.txt").write_text("hello " * 5000)
    long = work.read_document(str(tmp_path / "t.txt"))
    assert long.ok and "the rest was cut" in long.content


def test_unreadable_files_say_why(tmp_path):
    assert "not found" in work.read_document(str(tmp_path / "none.pdf")).content.lower()
    (tmp_path / "old.doc").write_bytes(b"x")
    assert ".docx" in work.read_document(str(tmp_path / "old.doc")).content
    (tmp_path / "x.exe").write_bytes(b"MZ")
    assert not work.read_document(str(tmp_path / "x.exe")).ok
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    assert not work.read_document(str(tmp_path / "bad.pdf")).ok


def test_submissions_are_read_a_few_at_a_time(tmp_path):
    from docx import Document

    for i in range(7):
        doc = Document()
        doc.add_paragraph(f"Answer of student {i}: " + "testing " * 600)
        doc.save(tmp_path / f"Student{i}.docx")
    (tmp_path / "notes.exe").write_bytes(b"MZ")
    first = work.read_submissions(str(tmp_path), count=5)
    assert first.ok and first.untrusted and "Submissions 1-5 of 7" in first.content
    assert "=== Student0.docx ===" in first.content and "start=5" in first.content
    assert len(first.content) < 5 * 2700
    last = work.read_submissions(str(tmp_path), start=5)
    assert "Student6.docx" in last.content and "last one" in last.content
    assert not work.read_submissions(str(tmp_path / "none")).ok


def test_read_document_is_registered_as_untrusted(registry):
    tool = registry.get("read_document")
    assert tool.risk == Risk.R0 and tool.untrusted_output


# ---- organise_folder ----------------------------------------------------------------


def old_file(path, content=b"x"):
    path.write_bytes(content)
    past = time.time() - 3600
    os.utime(path, (past, past))
    return path


def test_organise_plans_moves_and_undoes(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    for name in ("report.pdf", "marks.xlsx", "photo.JPG", "song.mp3", "setup.exe", "notes.txt"):
        old_file(downloads / name)
    (downloads / "fresh.pdf").write_bytes(b"still downloading")
    (downloads / "movie.mp4.crdownload").write_bytes(b"x")
    old_file(downloads / "unknown.xyz")
    (downloads / "Documents").mkdir()
    old_file(downloads / "Documents" / "report.pdf")  # a file with the same name is already there

    organiser = work.Organiser(tmp_path / "undo.json", home=home, blocked=[])
    plan = organiser.describe("downloads")
    assert "Move 6 files" in plan and "2 → Documents" in plan and "Nothing is deleted" in plan

    result = organiser.apply("Downloads")
    assert result.ok
    assert (downloads / "Documents" / "report (2).pdf").exists()
    assert (downloads / "Sheets" / "marks.xlsx").exists()
    assert (downloads / "Pictures" / "photo.JPG").exists()
    assert (downloads / "Installers" / "setup.exe").exists()
    assert (downloads / "fresh.pdf").exists() and (downloads / "unknown.xyz").exists()

    undone = organiser.undo()
    assert undone.ok and "6 files" in undone.content
    assert (downloads / "report.pdf").exists() and (downloads / "song.mp3").exists()
    assert not (downloads / "Music").exists()
    assert (downloads / "Documents" / "report.pdf").exists()
    assert not organiser.undo().ok


def test_organise_refuses_unsafe_folders(tmp_path):
    home = tmp_path / "home"
    (home / "project" / ".git").mkdir(parents=True)
    (home / "Rishu").mkdir()
    organiser = work.Organiser(tmp_path / "undo.json", home=home, blocked=[home / "Rishu"])
    assert "inside your user folder" in organiser.describe(str(home))
    assert "inside your user folder" in organiser.describe(str(tmp_path))
    assert "code project" in organiser.describe(str(home / "project"))
    assert "belongs to Rishu" in organiser.describe(str(home / "Rishu"))
    assert not organiser.apply(str(home)).ok


def test_organise_only_asks_when_it_moves(registry):
    tool = registry.get("organise_folder")
    assert tool.risk_for({"folder": "Downloads"}) == Risk.R0
    assert tool.risk_for({"folder": "Downloads", "apply": True}) == Risk.R2
    assert registry.get("undo_organise").risk == Risk.R2


# ---- dictation ------------------------------------------------------------------------


class FakeUser32:
    """Windows below Rishu in z-order: 1 Rishu (foreground) → 2 popup → 3 terminal or Word."""

    def __init__(self, windows):
        self.windows = windows  # hwnd -> (title, class, owner)
        self.foreground = 1
        self.keys = []

    def GetForegroundWindow(self):  # noqa: N802 - Win32 names
        return self.foreground

    def GetWindow(self, hwnd, cmd):  # noqa: N802
        if cmd == 2:
            return hwnd + 1 if hwnd + 1 in self.windows else 0
        return self.windows[hwnd][2]

    def IsWindowVisible(self, hwnd):  # noqa: N802
        return True

    def GetWindowTextW(self, hwnd, buffer, size):  # noqa: N802
        buffer.value = self.windows[hwnd][0]

    def GetClassNameW(self, hwnd, buffer, size):  # noqa: N802
        buffer.value = self.windows[hwnd][1]

    def keybd_event(self, vk, scan, flags, extra):
        self.keys.append((vk, flags))

    def SetForegroundWindow(self, hwnd):  # noqa: N802
        self.foreground = hwnd


def test_dictation_pastes_into_the_window_behind_rishu():
    user32 = FakeUser32(
        {1: ("Rishu", "FLUTTER", 0), 2: ("", "tooltip", 0), 3: ("Notes.docx - Word", "OpusApp", 0)}
    )
    copied = []
    typist = work.Typist(
        "win32", user32, sleep=lambda s: None, clipboard=lambda t: copied.append(t) or True
    )
    assert typist.target()[1] == "Notes.docx - Word"
    result = typist.type_into("नमस्ते class")
    assert result.ok and copied == ["नमस्ते class"]
    assert user32.foreground == 3 and (0x56, 0) in user32.keys


def test_dictation_never_types_into_a_terminal():
    user32 = FakeUser32(
        {1: ("Rishu", "FLUTTER", 0), 2: ("Windows PowerShell", "ConsoleWindowClass", 0)}
    )
    typist = work.Typist("win32", user32, sleep=lambda s: None, clipboard=lambda t: True)
    result = typist.type_into("rm -rf")
    assert not result.ok and "terminal" in result.content and not user32.keys


def test_dictation_elsewhere_and_its_approval(registry):
    assert not work.Typist("linux").type_into("hi").ok
    assert registry.get("type_text").risk == Risk.R2
    assert "the app behind Rishu" in registry.get("type_text").preview({"text": "hello"})
    assert not run(registry, "copy_to_clipboard", text="x").ok


# ---- deadlines ------------------------------------------------------------------------


def test_dates_people_say():
    today = date(2026, 11, 21)  # a Saturday
    assert work.parse_day("kal", today) == date(2026, 11, 22)
    assert work.parse_day("30 Nov", today) == date(2026, 11, 30)
    assert work.parse_day("10 jan", today) == date(2027, 1, 10)
    assert work.parse_day("5/12/2026", today) == date(2026, 12, 5)
    assert work.parse_day("friday", today) == date(2026, 11, 27)
    assert work.parse_day("shukravar", today) == date(2026, 11, 27)
    assert work.parse_day("5 din baad", today) == date(2026, 11, 26)
    assert work.parse_day("31/02", today) is None and work.parse_day("someday", today) is None


def test_deadlines_with_reminders(registry):
    added = run(
        registry, "deadline_add", title="Website for client", due="20 Nov", client="Sharma Traders"
    )
    assert added.ok and "Fri 20 Nov" in added.content  # "today" in the tests is Mon 16 Nov 2026
    assert len(registry.reminders.pending()) == 2
    run(registry, "deadline_add", title="Research paper", due="2026-12-30")
    listing = run(registry, "deadlines").content
    assert "Website for client for Sharma Traders" in listing and "in 4 days" in listing
    assert "Research paper" not in listing  # more than 30 days away
    assert "Research paper" in run(registry, "deadlines", days=60).content
    assert run(registry, "deadline_done", title="website").content.startswith("Marked 1")
    assert not run(registry, "deadline_add", title="X", due="whenever").ok


# ---- invoices -------------------------------------------------------------------------


def test_money_in_indian_style():
    assert work.indian_money(1234567.5) == "12,34,567.50"
    assert work.indian_money(999) == "999.00"
    assert work.rupees_in_words(125000) == "One lakh twenty-five thousand rupees only"
    assert work.rupees_in_words(10.5) == "Ten rupees and fifty paise only"


def test_invoice_file_numbers_and_totals(tmp_path):
    from docx import Document

    now = lambda: datetime(2026, 11, 21, 10, 0)  # noqa: E731
    items = [
        {"description": "Website design", "quantity": 1, "rate": 15000},
        {"description": "Hosting (months)", "quantity": 12, "rate": 250},
    ]
    first = work.make_invoice(
        "Sharma Traders",
        items,
        gst_percent=18,
        counter_path=tmp_path / "c.json",
        folder=tmp_path,
        now=now,
    )
    assert (
        first.ok
        and first.data["number"] == "INV-2026-001"
        and first.data["total"] == pytest.approx(21240)
    )
    text = "\n".join(p.text for p in Document(first.data["path"]).paragraphs)
    assert "Twenty-one thousand two hundred forty rupees only" in text
    second = work.make_invoice(
        "B",
        [{"description": "Talk", "rate": 5000}],
        counter_path=tmp_path / "c.json",
        folder=tmp_path,
        now=now,
    )
    assert second.data["number"] == "INV-2026-002"
    assert not work.make_invoice("C", [], counter_path=tmp_path / "c.json", folder=tmp_path).ok


# ---- morning briefing -----------------------------------------------------------------


def test_morning_briefing_brings_the_day_together(registry):
    run(
        registry,
        "timetable_add",
        entries=[{"day": "monday", "start": "10:00", "subject": "DAA", "group": "CSE 5 A"}],
    )
    registry.reminders.add("Call HOD", datetime(2026, 11, 16, 15, 0).timestamp())
    run(registry, "deadline_add", title="Sessional marks upload", due="18 Nov")
    text = run(registry, "morning_briefing").content
    assert "Monday 16 November 2026" in text
    assert "DAA (CSE 5 A)" in text and "Call HOD" in text and "Sessional marks upload" in text


# ---- meetings -------------------------------------------------------------------------


def test_meeting_is_recorded_in_chunks_and_transcribed(tmp_path):
    @contextmanager
    def source():
        def blocks():
            for _ in range(1300):  # 130 s of audio
                yield b"\x01\x00" * 1600
            while True:
                time.sleep(0.01)
                yield b"\x00\x00" * 1600

        yield blocks()

    heard = []
    meeting = work.MeetingRecorder(folder=tmp_path, clock=lambda: datetime(2026, 11, 21, 11, 0))
    assert not meeting.start("Dept meeting").ok  # not set up yet
    meeting.source = source
    meeting.transcribe = lambda wav: heard.append(len(wav)) or f"part {len(heard)}"
    meeting.ready = lambda: (True, "")
    assert meeting.start("Dept meeting").ok
    assert not meeting.start("again").ok
    deadline = time.time() + 5
    while len(heard) < 2 and time.time() < deadline:
        time.sleep(0.02)
    result = meeting.stop()
    assert (
        result.ok and result.untrusted and "part 1" in result.content and "part 2" in result.content
    )
    saved = list((tmp_path / "Meetings").glob("Dept meeting 2026-11-21 11-00*.txt"))
    assert saved and "part 1" in saved[0].read_text(encoding="utf-8")
    assert not meeting.stop().ok


def test_meeting_recording_asks_first(registry):
    assert registry.get("meeting_start").risk == Risk.R2
    assert "being recorded" in registry.get("meeting_start").preview({})
