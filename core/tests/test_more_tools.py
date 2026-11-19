import json
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from rishu_core.agent.factory import live_context
from rishu_core.api import CoreRuntime, create_app
from rishu_core.llm.mock import ScriptedLLM
from rishu_core.security import MemoryStore as SecretMemoryStore
from rishu_core.tools import build_registry
from rishu_core.tools.reminders import ReminderStore, parse_due
from rishu_core.tools.system import VK_VOLUME_DOWN, VK_VOLUME_MUTE, VK_VOLUME_UP, SystemControls
from rishu_core.tools.weather import weather

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 11, 20, 9, 0)


# ---- system controls --------------------------------------------------------


def test_volume_presses_media_keys():
    pressed = []
    controls = SystemControls(platform="win32", press=pressed.append)
    assert controls.volume("up", 3).ok
    assert controls.volume("down").ok
    assert controls.volume("mute").ok
    assert pressed == [VK_VOLUME_UP] * 3 + [VK_VOLUME_DOWN] * 5 + [VK_VOLUME_MUTE]
    assert not controls.volume("sideways").ok
    assert not SystemControls(platform="linux", press=pressed.append).volume("up").ok


def test_screenshot_uses_powershell_without_a_window(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        Path(args[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(args, 0)

    controls = SystemControls(platform="win32", run=run, pictures=tmp_path / "pics")
    result = controls.screenshot()
    assert result.ok and result.data["path"].endswith(".png")
    assert calls[0][1]["creationflags"] == 0x08000000


def test_lock_and_battery():
    controls = SystemControls(platform="win32", lock=lambda: True, battery=lambda: (76, True))
    assert controls.lock_pc().ok
    assert controls.battery().content == "Battery: 76% and charging."
    assert "no battery" in SystemControls(platform="win32", battery=lambda: None).battery().content


def test_lock_needs_approval(registry):
    assert registry.get("lock_computer").risk.label == "R2"


# ---- reminders ------------------------------------------------------------------


def test_parse_due():
    assert parse_due(5, None, NOW) == datetime(2026, 11, 20, 9, 5)
    assert parse_due(None, "17:30", NOW) == datetime(2026, 11, 20, 17, 30)
    assert parse_due(None, "5:30 pm", NOW) == datetime(2026, 11, 20, 17, 30)
    assert parse_due(None, "8 am", NOW) == datetime(2026, 11, 21, 8, 0)  # already past today
    assert parse_due(None, "25:00", NOW) is None
    assert parse_due(0, None, NOW) is None
    assert parse_due(None, None, NOW) is None


def test_reminder_tools_round_trip(registry):
    set_tool = registry.get("set_reminder")
    result = set_tool.handler(text="Paani piyo", minutes=10)
    assert result.ok and "Paani piyo" in result.content
    assert not set_tool.handler(text="x", at="never").ok
    listing = registry.get("list_reminders").handler()
    assert "Paani piyo" in listing.content
    ident = listing.data[0]["id"]
    assert registry.get("cancel_reminder").handler(id=ident).ok
    assert registry.get("list_reminders").handler().data == []


def test_due_reminders_pop_once(tmp_path):
    clock = [1000.0]
    store = ReminderStore(tmp_path / "r.json", clock=lambda: clock[0])
    store.add("early", 1005)
    store.add("late", 2000)
    assert store.pop_due() == []
    clock[0] = 1010
    assert [r["text"] for r in store.pop_due()] == ["early"]
    assert store.pop_due() == []
    assert [r["text"] for r in store.pending()] == ["late"]


class FakeSynth:
    name = "fake"

    def __init__(self):
        self.texts = []

    def available(self):
        return True

    def synth(self, text, gender, out_dir):
        from rishu_core.voice import Audio

        self.texts.append(text)
        path = Path(out_dir) / f"{len(self.texts)}.mp3"
        path.write_bytes(b"a")
        return Audio(path, "mp3")


class FakePlayer:
    def available(self):
        return True

    def play(self, path, kind, cancel):
        return True


def test_due_reminder_is_shown_and_spoken_in_the_open_window(settings, registry, tmp_path):
    from rishu_core.voice import VoiceEngine

    synth = FakeSynth()
    runtime = CoreRuntime(
        settings,
        token=TOKEN,
        home=tmp_path,
        secrets=SecretMemoryStore(),
        llm=ScriptedLLM([]),
        registry=registry,
        env={},
        voice=VoiceEngine(
            settings.defaults["voice"],
            settings.models["speech"],
            settings.models["providers"],
            lambda name: "",
            home=tmp_path,
            synthesizer=synth,
            player=FakePlayer(),
        ),
    )
    registry.reminders.add("HOD meeting", 0)  # already due
    assert runtime.check_reminders() == 0  # no window yet: kept
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"
        assert runtime.check_reminders() == 1
        event = json.loads(ws.receive_text())
        assert event == {"v": 1, "type": "reminder", "text": "HOD meeting"}
        for _ in range(4):
            if synth.texts:
                break
            json.loads(ws.receive_text())
    assert synth.texts == ["Yaad dila raha hoon: HOD meeting."] or synth.texts == [
        "Yaad dila raha hoon: HOD meeting"
    ]


# ---- memory ----------------------------------------------------------------------


def test_memory_is_saved_used_in_the_prompt_and_forgotten(registry):
    assert registry.get("remember").handler(fact="Mera favourite subject DAA hai").ok
    registry.get("remember").handler(fact="mera favourite subject daa hai")  # no duplicate
    assert len(registry.memory.load()) == 1
    context = live_context(registry)
    assert "Current local time" in context and "favourite subject daa" in context.lower()
    assert registry.get("forget").handler(about="DAA").ok
    assert not registry.get("forget").handler(about="DAA").ok
    assert "favourite" not in live_context(registry)
    assert "not saved anything" in registry.get("list_memories").handler().content


def test_agent_sends_memory_in_the_system_prompt(settings, tmp_path):
    from rishu_core.agent import build_agent

    reg = build_registry(
        settings, home=tmp_path, uri_opener=lambda u: True, url_opener=lambda u: True
    )
    reg.memory.add("User ka naam Neelesh hai")
    llm = ScriptedLLM(["Haan Neelesh!"])
    agent = build_agent(settings, llm=llm, registry=reg, use_router=False, home=tmp_path)
    agent.run_turn("mera naam kya hai?")
    system = llm.calls[0]["messages"][0]["content"]
    assert "User ka naam Neelesh hai" in system and "Current local time" in system


# ---- weather ----------------------------------------------------------------------


def test_weather_from_open_meteo():
    def handler(request):
        if "geocoding" in request.url.host:
            assert request.url.params["name"] == "Gurugram"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Gurugram",
                            "admin1": "Haryana",
                            "country": "India",
                            "latitude": 28.4,
                            "longitude": 77.0,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 21.4,
                    "apparent_temperature": 20.9,
                    "relative_humidity_2m": 55,
                    "weather_code": 1,
                    "wind_speed_10m": 6.1,
                },
                "daily": {
                    "temperature_2m_min": [12.0, 11.5],
                    "temperature_2m_max": [26.0, 25.0],
                    "precipitation_probability_max": [0, 10],
                },
            },
        )

    result = weather("Gurugram", transport=httpx.MockTransport(handler))
    assert result.ok
    assert "Gurugram, Haryana, India: mainly clear, 21.4°C" in result.content
    assert "Tomorrow 11.5–25.0°C" in result.content


def test_weather_unknown_place_and_offline():
    def nothing(request):
        return httpx.Response(200, json={})

    assert not weather("Atlantis", transport=httpx.MockTransport(nothing)).ok

    def down(request):
        raise httpx.ConnectError("offline", request=request)

    assert "not reachable" in weather("Delhi", transport=httpx.MockTransport(down)).content


# ---- vision -----------------------------------------------------------------------


def test_look_at_screen_sends_a_jpeg_and_marks_the_answer_untrusted(tmp_path):
    from rishu_core.tools.vision import look_at_screen

    asked = []

    def capture(path):
        path.write_bytes(b"\xff\xd8jpeg")
        return True

    def ask(question, jpeg):
        asked.append((question, jpeg))
        return "VS Code mein ek Python error dikh raha hai: NameError."

    result = look_at_screen("Yeh error kya hai?", capture, ask)
    assert result.ok and result.untrusted and "NameError" in result.content
    assert asked == [("Yeh error kya hai?", b"\xff\xd8jpeg")]
    assert not look_at_screen("x", lambda p: False, ask).ok
    assert not look_at_screen("x", capture, None).ok

    def broken(question, jpeg):
        raise RuntimeError("quota")

    assert "quota" in look_at_screen("x", capture, broken).content


def test_runtime_vision_call_uses_the_vision_role(settings, registry, tmp_path):
    seen = []

    class FakeLLM:
        def chat(self, role, messages, tools=None, stream=None):
            from rishu_core.llm import LLMResponse

            seen.append((role, messages))
            return LLMResponse(content="Ek browser khula hai.")

    runtime = CoreRuntime(
        settings,
        token=TOKEN,
        home=tmp_path,
        secrets=SecretMemoryStore(),
        llm=FakeLLM(),
        registry=registry,
        env={},
    )
    assert runtime.ask_vision("kya hai?", b"jpeg") == "Ek browser khula hai."
    role, messages = seen[0]
    assert role == "vision"
    image = messages[1]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/jpeg;base64,")
