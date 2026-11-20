"""Lexyta attendance on a stand-in page with the real structure (no real student data)."""

import http.server
import threading

import pytest
from test_browser import needs_chrome

from rishu_core.browser import Browser, ChromeLauncher
from rishu_core.tools.lexyta import LexytaAttendance, _preview, match_student

# 45 made-up students, 20 per page, like Lexyta's paginated attendance table.
PAGE = r"""<!doctype html><html><head><title>LMS | Lexyta</title></head><body>
<h3>Meeting attendance</h3><div id="pager"></div>
<ul id="list"></ul>
<button id="prev">Previous</button><button id="next">Next</button>
<button lexytatestid="attendance-lock" onclick="window.locked=true">Submit &amp; lock attendance</button>
<script>
const names = ['Aarav Shah','Diya Mehta','Kabir Rao','Isha Nair','Vivaan Gill','Anaya Bose','Reyansh Jain','Myra Das',
  'Arjun Pillai','Sara Khan','Vihaan Roy','Kiara Sen','Aditya Iyer','Riya Paul','Krish Malhotra'];
window.students = Array.from({length: 45}, (_, i) => ({
  name: names[i % names.length] + (i >= names.length ? ' ' + String.fromCharCode(65 + Math.floor(i / names.length)) : ''),
  roll: '24CSE' + String(i + 1).padStart(3, '0'), status: ''}));
let page = 0;
function render() {
  const list = document.getElementById('list'); list.innerHTML = '';
  for (const s of students.slice(page * 20, page * 20 + 20)) {
    const li = document.createElement('li');
    li.innerHTML = '<lms-user-column><span><span>' + s.name + '</span></span><span><span>' + s.roll +
      '</span><span>' + s.roll.toLowerCase() + '@college.example</span></span></lms-user-column>' +
      '<lexyta-segmented-control testid="attendance-mark"><div role="tablist" aria-label="Attendance status">' +
      ['Present','Late','Absent','Excused'].map(x => '<button type="button" role="tab" aria-selected="' + (s.status === x) + '">' + x + '</button>').join('') +
      '</div></lexyta-segmented-control>';
    li.querySelectorAll('[role=tab]').forEach(b => b.onclick = () => { s.status = b.innerText; render(); });
    list.appendChild(li);
  }
  document.getElementById('pager').innerText = (page * 20 + 1) + '-' + Math.min(45, page * 20 + 20) + ' of 45 items';
  document.getElementById('next').disabled = page >= 2;
}
document.getElementById('next').onclick = () => { page++; setTimeout(render, 150); };
document.getElementById('prev').onclick = () => { page = Math.max(0, page - 1); setTimeout(render, 150); };
render();
</script></body></html>"""


@pytest.fixture
def lexyta(tmp_path):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode())

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    browser = Browser(
        ChromeLauncher(tmp_path, extra_args=["--headless=new", "--no-sandbox", "--disable-gpu"])
    )
    url = f"http://127.0.0.1:{server.server_address[1]}/lexyta/classes/c1/meetings/m1/attendance"
    yield browser, url
    try:
        browser.session().call("Browser.close", timeout=5)
    except Exception:  # noqa: BLE001
        pass
    browser.close()
    server.shutdown()


@needs_chrome
def test_marks_every_page_and_locks_only_when_asked(lexyta):
    browser, url = lexyta
    browser.open(url)
    tool = LexytaAttendance(browser)
    result = tool.mark(absent=["5", "24CSE041"], late=["Kiara Sen"], everyone_else="present")
    assert result.ok, result.content
    assert (
        "Absent: 2" in result.content
        and "Late: 1" in result.content
        and "Present: 42" in result.content
    )
    assert "Not locked yet" in result.content
    # The page's own data (main world) shows the result on all three pages.
    model = browser.session().evaluate(
        "JSON.stringify(window.students.map(s => [s.roll, s.status]))"
    )
    marks = dict(__import__("json").loads(model))
    assert (
        marks["24CSE005"] == "Absent"
        and marks["24CSE041"] == "Absent"
        and marks["24CSE012"] == "Late"
    )
    assert sum(1 for v in marks.values() if v == "Present") == 42
    assert browser.session().evaluate("window.locked === true") is False
    locked = tool.mark(absent=["5", "24CSE041"], late=["Kiara Sen"], lock=True)
    assert locked.ok and "Submitted and locked" in locked.content
    assert browser.session().evaluate("window.locked === true") is True


@needs_chrome
def test_unknown_or_ambiguous_students_change_nothing(lexyta):
    browser, url = lexyta
    browser.open(url)
    tool = LexytaAttendance(browser)
    result = tool.mark(absent=["Aarav", "99"])
    assert (
        not result.ok
        and "more than one student" in result.content
        and 'no student matches "99"' in result.content
    )
    model = browser.session().evaluate("window.students.filter(s => s.status).length")
    assert model == 0


def test_needs_the_attendance_page_open():
    class Elsewhere:
        def run(self, *a, **k):
            return "https://lms.lexyta.com/my-courses"

    result = LexytaAttendance(Elsewhere()).mark(absent=["5"])
    assert not result.ok and "Open the meeting's attendance page" in result.content


def test_matching_and_preview():
    rows = [
        {"name": "Aryan Kumar", "roll": "22CSE005"},
        {"name": "Priya Sharma", "roll": "22CSE012"},
        {"name": "Aryan Singh", "roll": "2201010015"},
    ]
    assert [r["roll"] for r in match_student("5", rows)] == ["22CSE005"]
    assert [r["roll"] for r in match_student("15", rows)] == ["2201010015"]
    assert [r["roll"] for r in match_student("22cse012", rows)] == ["22CSE012"]
    assert len(match_student("Aryan", rows)) == 2 and len(match_student("aryan kumar", rows)) == 1
    text = _preview({"absent": ["5", "12"], "lock": True})
    assert "ABSENT: 5, 12" in text and "SUBMIT & LOCK" in text and "everyone else PRESENT" in text
