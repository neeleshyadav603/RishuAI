import pytest

from rishu_core import cli
from rishu_core.offline import Intent, parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rishu, Chrome kholo", Intent("open_app", {"name": "Chrome"})),
        ("hey rishu notepad khol do", Intent("open_app", {"name": "notepad"})),
        ("open file explorer", Intent("open_app", {"name": "file explorer"})),
        ("please launch calculator", Intent("open_app", {"name": "calculator"})),
        ("रिशु, क्रोम खोलो", Intent("open_app", {"name": "क्रोम"})),
        ("whatsapp ko open karo", Intent("open_app", {"name": "whatsapp"})),
        ("youtube.com kholo", Intent("open_url", {"url": "youtube.com"})),
        (
            "open https://gitm.edu.in/admission",
            Intent("open_url", {"url": "https://gitm.edu.in/admission"}),
        ),
        ("time kya hua hai?", Intent("get_time", {})),
        ("what time is it", Intent("get_time", {})),
        ("अभी कितने बजे हैं", Intent("get_time", {})),
        ("time", Intent("get_time", {})),
        ("note likho: kal 10 baje meeting", Intent("add_note", {"text": "kal 10 baje meeting"})),
        ("make a note that buy milk", Intent("add_note", {"text": "buy milk"})),
        ("नोट लिखो दूध लाना है", Intent("add_note", {"text": "दूध लाना है"})),
        ("mere notes dikhao", Intent("list_notes", {})),
        ("show my notes", Intent("list_notes", {})),
    ],
)
def test_parse_basic_commands(text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "quantum computing samjhao",
        "5 baje ka alarm lagao",
        "Rahul ko message bhejo",
        "",
        "rishu",
        "mujhe time management sikhao",
    ],
)
def test_parse_leaves_everything_else_to_the_llm(text):
    assert parse(text) is None


def test_cli_once_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RISHU_HOME", str(tmp_path))
    assert cli.main(["--offline", "--once", "note likho: demo ki taiyari"]) == 0
    out = capsys.readouterr().out
    assert "(Offline mode) Note saved: demo ki taiyari" in out
    assert (tmp_path / "notes.jsonl").exists()
    assert (tmp_path / "activity.jsonl").exists()


def test_console_approver(monkeypatch, capsys):
    from rishu_core.agent import ApprovalRequest
    from rishu_core.permissions import Decision, Risk

    request = ApprovalRequest("c1", "send", {}, Risk.R2, Decision.CONFIRM, "Send hi", "R2 action")
    approver = cli.ConsoleApprover()
    monkeypatch.setattr("builtins.input", lambda prompt="": "haan")
    assert approver.confirm(request)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert not approver.confirm(request)
    assert not approver.step_up(request)
    assert "two-factor" in capsys.readouterr().out
