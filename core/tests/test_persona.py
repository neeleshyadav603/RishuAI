"""Two personas (professional / personal) and the user's own personalisation."""

import pytest
from test_api import make_runtime

from rishu_core.agent import build_system_prompt
from rishu_core.user_settings import UserSettings
from rishu_core.voice.tts import EdgeSynthesizer


def test_professional_is_the_default(settings):
    prompt = build_system_prompt(settings)
    assert "Style: professional" in prompt and "Style: personal" not in prompt
    assert "masculine forms" in prompt  # default voice is male
    assert "You are an AI" in prompt


def test_personal_persona_with_address_and_about_me(settings):
    custom = settings.with_defaults(
        {
            "persona": "personal",
            "voice_gender": "female",
            "user_name": "Neelesh",
            "address_as": "Neelesh ji",
            "about_me": "Main GITM mein padhata hoon. Subah ki classes hoti hain.",
        }
    )
    prompt = build_system_prompt(custom)
    assert "Style: personal" in prompt and "Style: professional" not in prompt
    assert "feminine forms" in prompt
    assert 'Address the user as "Neelesh ji"' in prompt
    assert "GITM mein padhata hoon" in prompt
    # The warm style keeps the honesty and safety lines.
    assert "you are an AI and say so if asked" in prompt and "nothing sexual" in prompt


def test_unknown_persona_falls_back_to_professional(settings):
    prompt = build_system_prompt(settings.with_defaults({"persona": "pirate"}))
    assert "Style: professional" in prompt


def test_settings_validate_persona_and_texts(tmp_path):
    store = UserSettings(tmp_path / "settings.json")
    store.update({"persona": "personal", "address_as": "  Sir  ", "about_me": "Line one\nline   two"})
    assert store.load() == {"persona": "personal", "address_as": "Sir", "about_me": "Line one line two"}
    with pytest.raises(ValueError):
        store.update({"persona": "romantic"})
    with pytest.raises(ValueError):
        store.update({"about_me": "x" * 601})
    with pytest.raises(ValueError):
        store.update({"address_as": 5})


def test_persona_changes_the_speaking_rate(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, script=[])
    edge = [s for s in runtime.voice.synthesizer.synthesizers if isinstance(s, EdgeSynthesizer)]
    assert edge and edge[0].rate == "+5%"
    assert runtime.update_settings({"persona": "personal"})["persona"] == "personal"
    assert edge[0].rate == "-2%"
    runtime.update_settings({"persona": "professional"})
    assert edge[0].rate == "+5%"
