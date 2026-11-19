"""Personal data files (notes, memory, reminders) are encrypted at rest."""

import json
import sys

import pytest

from rishu_core.security.vault import HEADER, Vault
from rishu_core.tools.memory import MemoryStore
from rishu_core.tools.notes import NotesStore
from rishu_core.tools.reminders import ReminderStore


def fake_codec(data, protect):
    """Reversible stand-in for DPAPI; fails like DPAPI on a foreign blob."""
    if protect:
        return b"K" + bytes(b ^ 0x5A for b in data)
    if not data.startswith(b"K"):
        raise OSError(13, "DPAPI call failed")
    return bytes(b ^ 0x5A for b in data[1:])


def test_vault_encrypts_and_reads_back(tmp_path):
    vault = Vault(fake_codec)
    path = tmp_path / "memory.json"
    vault.write_text(path, '[{"text": "Mera favourite subject DAA hai"}]')
    raw = path.read_bytes()
    assert raw.startswith(HEADER) and b"DAA" not in raw
    assert "DAA" in vault.read_text(path)
    assert vault.read_text(tmp_path / "missing.json") is None


def test_old_plain_files_are_read_and_encrypted_on_the_next_write(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps([{"id": "a1", "text": "Purani baat", "ts": 1}]), encoding="utf-8")
    store = MemoryStore(path, vault=Vault(fake_codec))
    assert [f["text"] for f in store.load()] == ["Purani baat"]
    store.add("Nayi baat")
    assert b"Purani" not in path.read_bytes() and path.read_bytes().startswith(HEADER)
    assert [f["text"] for f in store.load()] == ["Purani baat", "Nayi baat"]


def test_a_file_that_cannot_be_decrypted_is_set_aside(tmp_path):
    path = tmp_path / "reminders.json"
    path.write_bytes(HEADER + b"bm90IG91cnM=\n")  # a blob from another Windows account
    store = ReminderStore(path, vault=Vault(fake_codec))
    assert store.pending() == []
    assert (tmp_path / "reminders.json.unreadable").exists()
    store.add("Paani piyo", 10**10)
    assert [r["text"] for r in store.pending()] == ["Paani piyo"]


def test_notes_and_reminders_are_encrypted(tmp_path):
    vault = Vault(fake_codec)
    notes = NotesStore(tmp_path / "notes.jsonl", vault=vault)
    notes.add("Kal 10 baje HOD meeting")
    notes.add("Lab file check karni hai")
    assert b"HOD" not in (tmp_path / "notes.jsonl").read_bytes()
    assert [n["text"] for n in notes.list()] == [
        "Kal 10 baje HOD meeting",
        "Lab file check karni hai",
    ]
    reminders = ReminderStore(tmp_path / "reminders.json", vault=vault)
    reminders.add("Paani piyo", 10**10)
    assert b"Paani" not in (tmp_path / "reminders.json").read_bytes()


def test_without_a_codec_files_stay_plain(tmp_path):
    vault = Vault(platform="linux")
    assert not vault.encrypted
    vault.write_text(tmp_path / "a.json", "[]")
    assert (tmp_path / "a.json").read_text() == "[]"
    # An encrypted file cannot be read without the codec, and is left alone.
    (tmp_path / "b.json").write_bytes(HEADER + b"eA==\n")
    assert vault.read_text(tmp_path / "b.json") is None and (tmp_path / "b.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")
def test_real_dpapi_round_trip(tmp_path):
    vault = Vault()
    assert vault.encrypted
    vault.write_text(tmp_path / "memory.json", "गुप्त बात")
    assert "गुप्त".encode() not in (tmp_path / "memory.json").read_bytes()
    assert vault.read_text(tmp_path / "memory.json") == "गुप्त बात"
