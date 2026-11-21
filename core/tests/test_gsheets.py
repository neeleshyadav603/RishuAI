"""Google Sheets through Rishu's browser: read by CSV, write through the Name Box, verify."""

import csv
import io

from rishu_core.permissions import Risk
from rishu_core.tools import gsheets

URL = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=42"


class FakeSheetBrowser:
    """A Google Sheet in a fake browser: the Name Box selects a cell, typing fills it."""

    def __init__(self, rows, signed_in=True, lose=()):
        self.rows = [list(r) for r in rows]
        self.signed_in = signed_in
        self.lose = set(lose)  # cells Google "drops" (to test the check)
        self.url = ""
        self.opened = []
        self.calls = []
        self._typing_address = False
        self._cell = None

    def open(self, url):
        self.opened.append(url)
        self.url = url

    def run(self, function, *args, timeout=20):
        if function == gsheets.FETCH_CSV:
            assert args == ("1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "42")
            if not self.signed_in:
                return {"status": 200, "text": "<html>Sign in</html>"}
            out = io.StringIO()
            csv.writer(out).writerows(self.rows)
            return {"status": 200, "text": out.getvalue()}
        if function == gsheets.FOCUS_NAME_BOX:
            self._typing_address = True
            return True
        raise AssertionError(function)

    def session(self):
        return self

    def call(self, method, params):
        self.calls.append((method, params))
        text = params["text"]
        if self._typing_address:
            col = ord(text[0]) - 65
            self._cell = (int(text[1:]) - 1, col)
        else:
            row, col = self._cell
            if text not in self.lose:
                while len(self.rows) <= row:
                    self.rows.append([])
                while len(self.rows[row]) <= col:
                    self.rows[row].append("")
                self.rows[row][col] = text

    def press(self, key):
        assert key == "enter"
        self._typing_address = False


ROWS = [
    ["DAA attendance B.Tech CSE 5 A", "", ""],
    ["Roll No", "Student Name", "20 Nov"],
    ["R1", "Aryan Kumar", "P"],
    ["R2", "Priya Sharma", "P"],
    ["R12", "Rohit Verma", "A"],
]


def sheets_for(browser):
    return gsheets.GoogleSheets(browser, sleep=lambda s: None)


def test_addresses_and_columns():
    assert gsheets.parse_url(URL) == ("1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "42")
    assert gsheets.parse_url("https://example.com/x") is None
    assert [gsheets.column_letter(i) for i in (0, 25, 26, 27, 701)] == ["A", "Z", "AA", "AB", "ZZ"]


def test_read_shows_the_sheet_as_untrusted_data():
    browser = FakeSheetBrowser(ROWS)
    result = gsheets.read_tool(sheets_for(browser), URL)
    assert result.ok and result.untrusted and "Roll No | Student Name | 20 Nov" in result.content
    assert "R12 | Rohit Verma | A" in result.content and browser.opened == [URL]


def test_not_signed_in_is_explained():
    result = gsheets.read_tool(sheets_for(FakeSheetBrowser(ROWS, signed_in=False)), URL)
    assert not result.ok and "Sign in to Google" in result.content


def test_fill_adds_a_column_writes_each_cell_and_checks_it():
    browser = FakeSheetBrowser(ROWS)
    sheets = sheets_for(browser)
    card = gsheets.preview(
        sheets,
        {"url": URL, "column": "21 Nov", "values": {"Aryan": "P", "roll 12": "A", "Priya": "P"}},
    )
    assert "(new column)" in card and "Rohit Verma / R12 ← A" in card
    result = gsheets.fill_tool(sheets, URL, "21 Nov", {"Aryan": "P", "roll 12": "A", "Priya": "P"})
    assert result.ok and "3 confirmed" in result.content
    assert (
        browser.rows[1][3] == "21 Nov" and browser.rows[2][3] == "P" and browser.rows[4][3] == "A"
    )
    addresses = [p["text"] for m, p in browser.calls][::2]
    assert addresses == ["D2", "D3", "D5", "D4"]


def test_unknown_people_stop_everything_and_lost_cells_are_reported():
    browser = FakeSheetBrowser(ROWS)
    blocked = gsheets.fill_tool(sheets_for(browser), URL, "20 Nov", {"Aryan": "A", "Kavya": "P"})
    assert not blocked.ok and "Kavya" in blocked.content and not browser.calls
    lossy = FakeSheetBrowser(ROWS, lose={"7"})
    result = gsheets.fill_tool(sheets_for(lossy), URL, "20 Nov", {"Aryan": "7", "Priya": "8"})
    assert not result.ok and "1 confirmed" in result.content and "Aryan Kumar" in result.content


def test_google_sheet_tools_are_registered(registry):
    assert registry.get("gsheet_fill").risk == Risk.R2
    assert registry.get("gsheet_read").untrusted_output
