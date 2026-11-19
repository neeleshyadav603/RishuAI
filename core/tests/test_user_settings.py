import json

import pytest

from rishu_core.user_settings import UserSettings


def test_update_validates_and_persists(tmp_path):
    store = UserSettings(tmp_path / "settings.json")
    assert store.load() == {}
    saved = store.update(
        {"user_name": "  Neelesh \n Yadav ", "language": "hi", "autonomy": "ask_always"}
    )
    assert saved == {"user_name": "Neelesh Yadav", "language": "hi", "autonomy": "ask_always"}
    store.update({"script": "devanagari", "streaming": False})
    assert UserSettings(tmp_path / "settings.json").load() == {
        "user_name": "Neelesh Yadav",
        "language": "hi",
        "autonomy": "ask_always",
        "script": "devanagari",
        "streaming": False,
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"language": "fr"},
        {"autonomy": "always_yes"},
        {"user_name": "x" * 61},
        {"user_name": 5},
        {"streaming": "yes"},
        {"policy": {"max_auto_risk": 3}},
        {"forbidden_tools": []},
    ],
)
def test_update_rejects_bad_or_unknown_settings(tmp_path, patch):
    store = UserSettings(tmp_path / "settings.json")
    with pytest.raises(ValueError):
        store.update(patch)
    assert not (tmp_path / "settings.json").exists()


def test_load_ignores_junk_in_the_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"language": "en", "autonomy": "root", "extra": 1}))
    assert UserSettings(path).load() == {"language": "en"}
    path.write_text("[1, 2]")
    assert UserSettings(path).load() == {}
