from datetime import datetime

import pytest

from rishu_core.config import load_settings
from rishu_core.tools import build_registry
from rishu_core.tools.apps import AppLauncher
from rishu_core.voice import engine as voice_engine
from rishu_core.voice.player import NullPlayer


class Spawned(list):
    """Records what the fake launcher was asked to start."""

    def __call__(self, kind, target):
        self.append((kind, target))


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def spawned():
    return Spawned()


@pytest.fixture
def opened_urls():
    return []


@pytest.fixture
def registry(settings, spawned, opened_urls, tmp_path):
    launcher = AppLauncher(
        settings.app_aliases,
        platform="win32",
        index={"google chrome": r"C:\menu\Google Chrome.lnk", "zoom": r"C:\menu\Zoom.lnk"},
        spawn=spawned,
        which=lambda name: None,
    )

    def search(query, limit):
        return [
            {
                "title": "AI news today",
                "url": "https://example.com/ai",
                "snippet": "Big AI update.",
            },
            {"title": "More AI", "url": "https://example.org/more", "snippet": "Another story."},
        ][:limit]

    return build_registry(
        settings,
        launcher=launcher,
        url_opener=lambda url: opened_urls.append(url) or True,
        search_backend=search,
        resolver=lambda host: ["93.184.216.34"],
        home=tmp_path,
        now=lambda: datetime(2026, 11, 16, 9, 30),
    )


@pytest.fixture(autouse=True)
def silent_voice(monkeypatch):
    """Tests never speak through the real sound card (Windows CI has one)."""
    monkeypatch.setattr(voice_engine, "default_player", NullPlayer)
