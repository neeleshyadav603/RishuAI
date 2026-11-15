import json

from rishu_core.config import data_dir, find_root, load_settings, read_prompt


def test_settings_load():
    settings = load_settings()
    assert settings.models["order"][0] in settings.models["providers"]
    for name in settings.models["order"]:
        provider = settings.models["providers"][name]
        assert provider["base_url"].startswith("http")
        assert set(provider["models"]) == {"fast", "smart", "coder", "vision"}
    assert "complete_payment" in settings.policy["forbidden_tools"]
    assert settings.policy["max_auto_risk"] == 2
    assert "chrome" in settings.app_aliases["windows"]


def test_prompts_exist():
    assert "Rishu" in read_prompt("persona_rishu")
    assert "untrusted_content" in read_prompt("system_rules")


def test_protocol_schema_is_valid_json():
    schema = json.loads(
        (find_root() / "shared" / "protocol" / "events.schema.json").read_text(encoding="utf-8")
    )
    names = {ref["$ref"].split("/")[-1] for ref in schema["oneOf"]}
    assert names <= set(schema["$defs"])
    assert {"user_message", "tool_call_proposed", "approval_response", "stop"} <= names


def test_data_dir_uses_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RISHU_HOME", str(tmp_path / "home"))
    assert data_dir() == tmp_path / "home"
    assert (tmp_path / "home").is_dir()
