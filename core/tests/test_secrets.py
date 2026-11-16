import json
import sys

import pytest

from rishu_core.security import MemoryStore, clean_secret, open_secret_store
from rishu_core.security.secrets import DpapiStore, KeyringStore


def fake_codec(data: bytes, *, protect: bool) -> bytes:
    """Stands in for DPAPI: reversible and clearly not the plain text."""
    return data[::-1] + b"!" if protect else data[:-1][::-1]


def test_clean_secret_trims_and_rejects_bad_keys():
    assert clean_secret("  gsk_abc123\n") == "gsk_abc123"
    for bad in ("", "   ", "has space", "line\nbreak", "x" * 600):
        with pytest.raises(ValueError):
            clean_secret(bad)


def test_memory_store_round_trip():
    store = MemoryStore()
    store.set("GROQ_API_KEY", "k1")
    assert store.get("GROQ_API_KEY") == "k1"
    store.delete("GROQ_API_KEY")
    assert store.get("GROQ_API_KEY") is None
    assert store.persistent is False


def test_dpapi_store_never_writes_plain_text(tmp_path):
    store = DpapiStore(tmp_path / "secrets.json", codec=fake_codec)
    store.set("GROQ_API_KEY", "gsk_secret_value")
    store.set("GEMINI_API_KEY", "AIza_other")
    raw = (tmp_path / "secrets.json").read_text()
    assert "gsk_secret_value" not in raw and "AIza_other" not in raw
    assert set(json.loads(raw)) == {"GROQ_API_KEY", "GEMINI_API_KEY"}
    # A new instance (next start of Rishu) reads them back.
    again = DpapiStore(tmp_path / "secrets.json", codec=fake_codec)
    assert again.get("GROQ_API_KEY") == "gsk_secret_value"
    again.delete("GROQ_API_KEY")
    assert again.get("GROQ_API_KEY") is None
    assert again.get("GEMINI_API_KEY") == "AIza_other"


def test_dpapi_store_survives_a_damaged_file(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text("not json")
    store = DpapiStore(path, codec=fake_codec)
    assert store.get("X") is None
    store.set("X", "value")
    assert store.get("X") == "value"
    path.write_text(json.dumps({"X": "%%%not-base64%%%"}))
    assert store.get("X") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI exists only on Windows")
def test_real_dpapi_round_trip(tmp_path):
    store = open_secret_store(tmp_path)
    assert store.kind == "dpapi"
    store.set("GROQ_API_KEY", "gsk_real_dpapi_ कुंजी")
    assert "gsk_real_dpapi" not in (tmp_path / "secrets.json").read_text()
    assert open_secret_store(tmp_path).get("GROQ_API_KEY") == "gsk_real_dpapi_ कुंजी"


def test_keyring_store_uses_the_backend():
    class Backend:
        def __init__(self):
            self.items = {}

        def get_password(self, service, name):
            return self.items.get((service, name))

        def set_password(self, service, name, value):
            self.items[(service, name)] = value

        def delete_password(self, service, name):
            del self.items[(service, name)]

    backend = Backend()
    store = KeyringStore(backend)
    store.set("K", "v")
    assert backend.items == {("Rishu", "K"): "v"} and store.get("K") == "v"
    store.delete("K")
    store.delete("K")  # deleting a missing secret is fine
    assert store.get("K") is None


def test_open_store_falls_back_to_memory_without_a_keyring(tmp_path, monkeypatch):
    monkeypatch.setattr("rishu_core.security.secrets._working_keyring", lambda: None)
    assert open_secret_store(tmp_path, platform="linux").kind == "memory"
    assert open_secret_store(tmp_path, platform="win32").kind == "dpapi"
