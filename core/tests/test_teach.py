"""Teach mode: record a task once in a real (headless) Chrome, run it with new values."""

import json

import pytest
from test_browser import needs_chrome

from rishu_core.browser import Browser, ChromeLauncher
from rishu_core.security.vault import Vault
from rishu_core.teach import SkillStore, build_skill
from rishu_core.tools import ToolRegistry
from rishu_core.tools import teach as teach_tools

MARKS = """<!doctype html><html><head><title>Gradebook</title></head><body>
<h1>Assignment 1 gradebook</h1>
<input lexytatestid="search-input" placeholder="Search students" onkeydown="if(event.key==='Enter')filter(this.value)">
<ul id="list">
<li data-n="Aryan Kumar">Aryan Kumar 21CSE001 <input type="number" aria-label="Marks"> <button onclick="save(this)">Save</button> <span class="st"></span></li>
<li data-n="Priya Sharma">Priya Sharma 21CSE002 <input type="number" aria-label="Marks"> <button onclick="save(this)">Save</button> <span class="st"></span></li>
<li data-n="Rohit Verma">Rohit Verma 21CSE003 <input type="number" aria-label="Marks"> <button onclick="save(this)">Save</button> <span class="st"></span></li>
</ul>
<script>
function filter(q){for(const li of document.querySelectorAll('#list li'))li.style.display=li.dataset.n.toLowerCase().includes(q.toLowerCase())?'':'none';}
function save(b){const li=b.parentNode;li.dataset.saved=li.querySelector('input').value;li.querySelector('.st').textContent='Saved';}
</script></body></html>"""


@pytest.fixture
def site():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = MARKS.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/gradebook"
    server.shutdown()


@pytest.fixture
def teach(tmp_path):
    launcher = ChromeLauncher(
        tmp_path / "home", extra_args=["--headless=new", "--no-sandbox", "--disable-gpu"]
    )
    browser = Browser(launcher)
    registry = ToolRegistry()
    tools = teach_tools.register(
        registry, browser, SkillStore(tmp_path / "skills.json", vault=Vault(platform="linux"))
    )
    yield tools, browser, registry
    try:
        browser.session().call("Browser.close", timeout=5)
    except Exception:  # noqa: BLE001
        pass
    browser.close()


def saved(browser):
    return browser.run(
        "() => Object.fromEntries(Array.from(document.querySelectorAll('#list li')).map(li => [li.dataset.n, li.dataset.saved || '']))"
    )


@needs_chrome
def test_learn_once_then_do_it_with_new_values(teach, site):
    tools, browser, registry = teach
    browser.open(site)
    events = []
    tools.listeners.append(events.append)
    assert tools.start("assignment marks").ok
    # The user shows the task (real input events, like a person in the window).
    page = browser.outline()
    search = next(i["ref"] for i in page["items"] if i["name"] == "Search students")
    browser.type(search, "Priya Sharma", press_enter=True)
    page = browser.outline()
    marks = next(i["ref"] for i in page["items"] if i["name"] == "Marks" and "Priya" in i["row"])
    browser.type(marks, "8")
    page = browser.outline()
    save = next(i["ref"] for i in page["items"] if i["name"] == "Save" and "Priya" in i["row"])
    browser.click(save)
    assert saved(browser)["Priya Sharma"] == "8"
    result = tools.stop("Assignment marks", "Enter one student's marks in the gradebook")
    assert result.ok, result.content
    assert events[-1]["recording"] is False and events[-2]["recording"] is True
    tool = registry.get("skill_assignment_marks")
    assert tool is not None and set(tool.parameters["required"]) == {"search_students", "marks"}
    preview = tool.preview({"search_students": "Aryan Kumar", "marks": "9"})
    assert (
        'Type "Aryan Kumar" into "Search students"' in preview
        and 'Type "9" into "Marks"' in preview
    )
    # Next time: a fresh page and new values.
    browser.open(site + "?again")
    done = tool.handler(search_students="Aryan Kumar", marks="9")
    assert done.ok, done.content
    assert saved(browser) == {"Aryan Kumar": "9", "Priya Sharma": "", "Rohit Verma": ""}
    assert not tool.handler(
        search_students="Rohit Verma", marks=""
    ).ok  # asks for the missing value
    assert "Assignment marks" in tools.list().content


@needs_chrome
def test_a_missing_control_stops_and_asks_to_be_shown_again(teach, site):
    tools, browser, registry = teach
    browser.open(site)
    tools.start("marks")
    page = browser.outline()
    marks = next(i["ref"] for i in page["items"] if i["name"] == "Marks" and "Rohit" in i["row"])
    browser.type(marks, "7")
    page = browser.outline()
    browser.click(
        next(i["ref"] for i in page["items"] if i["name"] == "Save" and "Rohit" in i["row"])
    )
    tools.stop("Rohit marks")
    browser.run("() => { document.querySelector('[data-n=\"Rohit Verma\"]').remove(); }")
    result = registry.get("skill_rohit_marks").handler(marks="5")
    assert not result.ok and "show you this task once more" in result.content


def test_build_skill_turns_typed_values_into_parameters():
    raw = [
        {
            "kind": "type",
            "target": {"name": "Search students", "role": "textbox"},
            "value": "Priya",
            "at": 1,
        },
        {"kind": "press", "key": "Enter", "target": {"name": "Search students"}, "at": 2},
        {
            "kind": "type",
            "target": {"name": "Search students", "role": "textbox"},
            "value": "Priya",
            "at": 3,
        },
        {"kind": "navigated", "url": "https://lms.example/x", "at": 4},
        {
            "kind": "click",
            "target": {"name": "Absent", "role": "tab", "row": "Priya Sharma 21CSE002"},
            "at": 5,
        },
        {"kind": "navigated", "url": "https://lms.example/y", "at": 9000},
    ]
    skill = build_skill("Mark absent", "", raw, "https://lms.example/meetings")
    assert [s.action for s in skill.steps] == ["open", "type", "press", "click", "open"]
    assert skill.params[0].name == "search_students" and skill.params[0].example == "Priya"
    assert skill.steps[3].target["row"] == "{{search_students}}"
    assert skill.steps[3].text({"search_students": "Rohit"}) == 'Click "Absent" (row: Rohit)'


def test_skills_are_saved_encrypted_and_replaced_by_name(tmp_path):
    def codec(data, protect):
        return bytes(b ^ 7 for b in data)

    store = SkillStore(tmp_path / "skills.json", vault=Vault(codec))
    one = build_skill("LMS marks", "v1", [{"kind": "click", "target": {"name": "Save"}}])
    store.save(one)
    assert b"Save" not in (tmp_path / "skills.json").read_bytes()
    store.save(build_skill("lms  marks", "v2", [{"kind": "click", "target": {"name": "Submit"}}]))
    skills = store.load()
    assert len(skills) == 1 and skills[0].description == "v2" and skills[0].id == one.id
    assert json.dumps(skills[0].to_dict())
    assert store.delete("LMS marks") and store.load() == []
