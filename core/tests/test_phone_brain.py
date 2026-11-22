"""The phone's brain file (app/assets/brain.json) matches config/models.yaml and the prompts."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phone_brain_is_up_to_date():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_phone_brain.py"), "--check"])
    assert result.returncode == 0, "run: python scripts/make_phone_brain.py"


def test_phone_brain_offline_model_matches_the_laptop_choices():
    import yaml

    brain = json.loads((ROOT / "app" / "assets" / "brain.json").read_text(encoding="utf-8"))
    config = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))["local_model"]
    local = brain["local_model"]
    assert local["default"] == config["default"] and set(local["choices"]) == set(config["choices"])
    assert local["choices"]["small"]["repo"] == config["choices"]["small"]["repo"]
    assert local["quants"][0] == "Q4_K_M"


def test_phone_brain_has_no_local_providers_and_no_keys():
    brain = json.loads((ROOT / "app" / "assets" / "brain.json").read_text(encoding="utf-8"))
    assert brain["order"] and "rishu_local" not in brain["providers"] and "ollama" not in brain["providers"]
    text = json.dumps(brain)
    assert "gsk_" not in text and "api_key" not in text
    assert brain["prompts"]["rules"].startswith("Rules on the phone")
