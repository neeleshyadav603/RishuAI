"""Excel / CSV: find, read, fill a column by person (made-up names only)."""

import csv

import openpyxl

from rishu_core.tools import sheets, vision


def make_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DAA A"
    ws.append(["GITM attendance register"])  # a title row above the header
    ws.append(["S.No", "Student Name", "Roll No", "Assignment 1"])
    ws.append([1, "Aryan Kumar", "22CSE005", 7])
    ws.append([2, "Priya Sharma", "22CSE012", None])
    ws.append([3, "Aryan Singh", "22CSE015", None])
    ws.append([4, "Mehak Gill", "22CSE021", "=SUM(1,2)"])
    wb.save(path)


def test_find_files_newest_first(tmp_path):
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Downloads" / "DAA_attendance.xlsx").write_text("x")
    (tmp_path / "Documents" / "old").mkdir(parents=True)
    (tmp_path / "Documents" / "old" / "daa attendance 2025.csv").write_text("x")
    result = sheets.find_files("daa attendance", sheets.user_folders(tmp_path))
    assert result.ok and len(result.data) == 2
    assert not sheets.find_files("nothing here", sheets.user_folders(tmp_path)).ok


def test_read_and_fill_xlsx_by_name_roll_and_last_digits(tmp_path):
    path = tmp_path / "marks.xlsx"
    make_xlsx(path)
    read = sheets.read_sheet(str(path))
    assert (
        read.ok and read.untrusted and "Student Name" in read.content and "4 rows" in read.content
    )
    values = {"Priya": "9", "15": "6", "22CSE021": "8", "aryan kumar": "10"}
    preview = sheets.preview_fill({"path": str(path), "column": "Assignment 1", "values": values})
    assert "Priya Sharma / 22CSE012 ← 9" in preview and "Aryan Singh / 22CSE015 ← 6" in preview
    done = sheets.fill_sheet(str(path), "Assignment 1", values, backup_dir=tmp_path / "backups")
    assert done.ok, done.content
    ws = openpyxl.load_workbook(path)["DAA A"]
    assert [ws.cell(r, 4).value for r in range(3, 7)] == [10, 9, 6, 8]  # numbers stay numbers
    assert len(list((tmp_path / "backups").iterdir())) == 1


def test_ambiguous_or_unknown_people_write_nothing(tmp_path):
    path = tmp_path / "marks.xlsx"
    make_xlsx(path)
    result = sheets.fill_sheet(str(path), "Assignment 1", {"Aryan": "5", "Zoya": "4"})
    assert (
        not result.ok
        and "several rows" in result.content
        and 'no row matches "Zoya"' in result.content
    )
    ws = openpyxl.load_workbook(path).active
    assert ws.cell(3, 4).value == 7


def test_spelling_slip_and_new_column_in_csv(tmp_path):
    path = tmp_path / "att.csv"
    path.write_text("Name,Roll\nAryan Kumar,22CSE005\nPriya Sharma,22CSE012\n", encoding="utf-8")
    result = sheets.fill_sheet(str(path), "21 Nov", {"Aryaan Kumar": "P", "priya": "A"})
    assert result.ok, result.content
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows == [
        ["Name", "Roll", "21 Nov"],
        ["Aryan Kumar", "22CSE005", "P"],
        ["Priya Sharma", "22CSE012", "A"],
    ]


def test_read_image_shrinks_and_marks_untrusted(tmp_path):
    photo = tmp_path / "register.jpg"
    photo.write_bytes(b"\xff\xd8fakejpeg")
    asked = []

    def ask(question, picture):
        asked.append((question, picture))
        return "Aryan Kumar | 22CSE005 | 5"

    no_shrink = lambda src, dst: False  # noqa: E731 - not on Windows: the small JPG is sent as is
    result = vision.read_image(
        str(photo), "rows as name | roll | count", no_shrink, ask, tmp_path / "tmp"
    )
    assert result.ok and result.untrusted and asked[0][1] == b"\xff\xd8fakejpeg"
    assert not vision.read_image(str(tmp_path / "x.jpg"), "q", no_shrink, ask, tmp_path).ok
    assert not vision.read_image(str(photo), "q", no_shrink, None, tmp_path).ok
