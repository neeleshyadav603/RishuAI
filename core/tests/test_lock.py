"""Locking Rishu: PIN, spoken password, Windows Hello, panic phrase, idle lock."""

import json

import pytest
from fastapi.testclient import TestClient
from test_api import AUTH, make_runtime, read_until, say

from rishu_core.api import create_app
from rishu_core.security import LockManager, MemoryStore, WindowsHello, is_panic_phrase
from rishu_core.security.lock import MAX_FAILURES, PHRASE_SECRET


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_lock(tmp_path, **kwargs):
    return LockManager(tmp_path / "lock.json", **kwargs)


def test_no_pin_means_never_locked(tmp_path):
    lock = make_lock(tmp_path)
    assert not lock.locked and not lock.pin_set
    assert lock.lock() is False and not lock.locked
    assert lock.status()["locked"] is False


def test_pin_rules_and_hashing(tmp_path):
    lock = make_lock(tmp_path)
    for bad in ("12", "abcd", "12 34", "1" * 13):
        with pytest.raises(ValueError):
            lock.set_pin(bad)
    lock.set_pin("4826")
    stored = (tmp_path / "lock.json").read_text()
    assert "4826" not in stored and "hash" in stored  # only a salted hash on disk
    with pytest.raises(PermissionError):
        lock.set_pin("1111", current="0000")  # changing needs the current PIN
    lock.set_pin("135790", current="4826")
    # A new manager (next start) begins locked once a PIN exists.
    again = make_lock(tmp_path)
    assert again.locked
    assert again.unlock_pin("4826") == (False, "wrong")
    assert again.unlock_pin("135790") == (True, "unlocked")


def test_wrong_pins_cause_a_pause(tmp_path):
    clock = Clock()
    lock = make_lock(tmp_path, clock=clock)
    lock.set_pin("4826")
    lock.lock()
    for _ in range(MAX_FAILURES - 1):
        assert lock.unlock_pin("0000") == (False, "wrong")
    assert lock.unlock_pin("0000") == (False, "paused")
    assert lock.unlock_pin("4826") == (False, "paused")  # even the right PIN waits
    clock.now += 31
    assert lock.unlock_pin("4826") == (True, "unlocked")


def test_spoken_password_is_encrypted_and_fuzzy(tmp_path):
    secrets = MemoryStore()
    lock = make_lock(tmp_path, secrets=secrets)
    with pytest.raises(PermissionError):
        lock.set_phrase("neela aasmaan bahut sundar hai")  # needs a PIN first
    lock.set_pin("4826")
    with pytest.raises(ValueError):
        lock.set_phrase("haan")
    lock.set_phrase("Neela aasmaan, bahut sundar hai!")
    assert lock.phrase_set
    assert "aasmaan" not in (tmp_path / "lock.json").read_text()
    assert secrets.get(PHRASE_SECRET) == "neelaaasmaanbahutsundarhai"
    lock.lock()
    assert lock.unlock_phrase("kuch aur hi bol diya") == (False, "wrong")
    assert lock.unlock_phrase("neela aasman bahut sundar hai") == (
        True,
        "unlocked",
    )  # STT spelling drift
    lock.remove_pin("4826")
    assert not lock.pin_set and not lock.phrase_set and secrets.get(PHRASE_SECRET) is None


def test_panic_phrases():
    for text in (
        "Rishu lock",
        "rishu, lock karo",
        "Hey Rishu lock.",
        "रिशु लॉक करो",
        "Rishu so jao",
    ):
        assert is_panic_phrase(text), text
    for text in ("Rishu lock screen kaise karte hain?", "lock karo", "PC lock karo"):
        assert not is_panic_phrase(text), text


def test_idle_lock(tmp_path):
    clock = Clock()
    lock = make_lock(tmp_path, clock=clock, idle_minutes=10)
    assert not lock.idle_due()  # no PIN, never
    lock.set_pin("4826")
    lock.unlock_pin("4826")
    lock.locked = False
    clock.now += 9 * 60
    assert not lock.idle_due()
    lock.touch()
    clock.now += 10 * 60
    assert lock.idle_due()


def test_windows_hello_only_on_windows(tmp_path):
    calls = []

    class Result:
        def __init__(self, code):
            self.returncode, self.stdout = code, ""

    def run(cmd, **kwargs):
        calls.append(cmd[-2])
        return Result(0)

    assert not WindowsHello(tmp_path, platform="linux", run=run).available()
    hello = WindowsHello(tmp_path, platform="win32", run=run)
    assert not hello.known()  # not checked yet: the status never waits for it
    assert hello.available() and hello.verify() and hello.known()
    assert calls == ["check", "verify"]
    lock = make_lock(tmp_path, hello=hello)
    lock.set_pin("4826")
    lock.lock()
    assert lock.unlock_hello() == (True, "unlocked")


# ---- over the API ----------------------------------------------------------------


def locked_runtime(settings, registry, tmp_path, script=None):
    runtime = make_runtime(settings, registry, tmp_path, script=script or [])
    runtime.lock.set_pin("4826")
    runtime.lock.lock()
    return runtime


def test_locked_window_refuses_until_pin(settings, registry, tmp_path):
    runtime = locked_runtime(settings, registry, tmp_path, script=["Namaste!"])
    client = TestClient(create_app(runtime))
    assert client.get("/v1/settings", headers=AUTH).status_code == 423
    assert client.get("/v1/activity", headers=AUTH).status_code == 423
    assert client.get("/v1/lock", headers=AUTH).json()["locked"] is True
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello" and hello["lock"]["locked"] is True
        events = read_until(ws, "state_change")
        assert events[-1]["state"] == "locked"
        say(ws, "Namaste")
        assert read_until(ws, "error")[-1]["code"] == "locked"
        ws.send_text(json.dumps({"v": 1, "type": "unlock", "method": "pin", "pin": "0000"}))
        events = read_until(ws, "error")
        assert any(e["type"] == "lock_state" and e["locked"] for e in events)
        ws.send_text(json.dumps({"v": 1, "type": "unlock", "method": "pin", "pin": "4826"}))
        events = read_until(ws, "lock_state")
        assert events[-1]["locked"] is False
        assert client.get("/v1/settings", headers=AUTH).status_code == 200
        say(ws, "Namaste")
        assert read_until(ws, "assistant_message")[-1]["text"] == "Namaste!"


def test_panic_phrase_locks_and_needs_a_pin(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, script=[])
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        json.loads(ws.receive_text())
        say(ws, "Rishu lock")
        assert read_until(ws, "notice")[-1]["text"].startswith("Lock karne ke liye")
        response = client.put("/v1/lock/pin", headers=AUTH, json={"pin": "4826"})
        assert response.status_code == 200 and response.json()["pin_set"] is True
        assert read_until(ws, "lock_state")[-1]["pin_set"] is True
        say(ws, "Rishu lock karo")
        events = read_until(ws, "state_change")
        assert any(e["type"] == "lock_state" and e["locked"] for e in events)
        assert events[-1]["state"] == "locked"
        assert client.put("/v1/lock/pin", headers=AUTH, json={"pin": "1111"}).status_code == 423


def test_pin_change_and_removal_need_the_current_pin(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, script=[])
    client = TestClient(create_app(runtime))
    assert client.put("/v1/lock/pin", headers=AUTH, json={"pin": "12"}).status_code == 422
    assert client.put("/v1/lock/pin", headers=AUTH, json={"pin": "4826"}).status_code == 200
    assert client.put("/v1/lock/pin", headers=AUTH, json={"pin": "1111"}).status_code == 403
    assert client.post("/v1/lock/remove", headers=AUTH, json={"current": "0000"}).status_code == 403
    response = client.post("/v1/lock/remove", headers=AUTH, json={"current": "4826"})
    assert response.status_code == 200 and response.json()["pin_set"] is False


def test_reminders_wait_while_locked(settings, registry, tmp_path):
    runtime = locked_runtime(settings, registry, tmp_path)
    spoken = []
    registry.reminders.add("HOD meeting", 0)
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        json.loads(ws.receive_text())
        session = runtime.active_session
        session.speaker.say = lambda text, gender: spoken.append(text) or True
        assert runtime.check_reminders() == 0
        assert runtime.check_reminders() == 0
        assert spoken == [
            "Ek reminder ka time ho gaya hai. Unlock karke dekho."
        ]  # once, no details
        runtime.lock.unlock_pin("4826")
        assert runtime.check_reminders() == 1
        assert spoken[-1].startswith("Yaad dila raha hoon: HOD meeting")
