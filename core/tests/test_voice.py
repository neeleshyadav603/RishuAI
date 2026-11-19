import json
import math
import struct
import subprocess
import sys
import threading
import time
from array import array
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from rishu_core.api import CoreRuntime, create_app
from rishu_core.llm.mock import ScriptedLLM
from rishu_core.security import MemoryStore
from rishu_core.voice import (
    Audio,
    ChainSynthesizer,
    GroqTranscriber,
    Recorder,
    Speaker,
    SttError,
    TtsError,
    VoiceEngine,
    clean_for_speech,
    is_devanagari,
    split_for_speech,
    to_wav,
)
from rishu_core.voice.mic import level_of, rms
from rishu_core.voice.tts import SapiSynthesizer

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ---- text ---------------------------------------------------------------


def test_clean_for_speech_drops_markdown_links_and_code():
    text = "## Qubit\n\n**Qubit** ek `bit` jaisa hai.\n- Pehla point\n- Doosra point\n```py\nprint(1)\n```\nSee [docs](https://x.org) or https://y.org"
    cleaned = clean_for_speech(text)
    assert "**" not in cleaned and "#" not in cleaned and "print(1)" not in cleaned
    assert "https" not in cleaned and "docs" in cleaned
    assert "Qubit. Qubit ek bit jaisa hai. Pehla point. Doosra point." in cleaned


def test_split_for_speech_keeps_first_chunk_short_and_respects_limits():
    text = (
        "Namaste Neelesh! "
        + "Quantum computing ek naya tareeka hai. " * 12
        + "यह बहुत रोचक है। ठीक है?"
    )
    chunks = split_for_speech(text, max_chars=120)
    assert chunks[0] == "Namaste Neelesh!" or len(chunks[0]) <= 90
    assert all(len(c) <= 120 for c in chunks)
    assert " ".join(chunks).replace("  ", " ").startswith("Namaste Neelesh!")
    assert chunks[-1].endswith("ठीक है?")
    assert split_for_speech("   ") == []
    long_word_run = "a" * 500
    assert all(len(c) <= 220 for c in split_for_speech(long_word_run))


def test_is_devanagari():
    assert is_devanagari("नमस्ते नीलेश, कैसे हो?")
    assert is_devanagari("Chrome खोल दिया है, अब बताओ")
    assert not is_devanagari("Chrome khol diya hai.")
    assert not is_devanagari("12345")


# ---- speech to text --------------------------------------------------------


def stt_transport(responses, seen):
    def handler(request):
        seen.append(request)
        status, body = responses.pop(0)
        return (
            httpx.Response(status, json=body)
            if isinstance(body, dict)
            else httpx.Response(status, text=body)
        )

    return httpx.MockTransport(handler)


def test_transcriber_sends_wav_and_falls_back_to_the_next_model():
    seen = []
    transport = stt_transport(
        [
            (404, {"error": {"message": "The model `old` does not exist"}}),
            (200, {"text": " Chrome kholo "}),
        ],
        seen,
    )
    stt = GroqTranscriber("https://groq.test/openai/v1", "k", ["old", "new"], transport=transport)
    assert stt.transcribe(b"RIFFdata", language="hi") == "Chrome kholo"
    last = seen[-1]
    assert last.url.path == "/openai/v1/audio/transcriptions"
    assert last.headers["authorization"] == "Bearer k"
    body = last.content
    assert b'name="model"\r\n\r\nnew' in body and b'name="language"\r\n\r\nhi' in body
    assert b"RIFFdata" in body and b'filename="speech.wav"' in body


@pytest.mark.parametrize(("status", "code"), [(401, "auth"), (429, "quota"), (500, "error")])
def test_transcriber_errors(status, code):
    stt = GroqTranscriber(
        "https://g.test/v1", "k", ["m"], transport=stt_transport([(status, {})], [])
    )
    with pytest.raises(SttError) as error:
        stt.transcribe(b"x")
    assert error.value.code == code


def test_transcriber_needs_a_key_and_network():
    with pytest.raises(SttError) as error:
        GroqTranscriber("https://g.test/v1", "", ["m"])
    assert error.value.code == "no_key"

    def down(request):
        raise httpx.ConnectError("no network", request=request)

    stt = GroqTranscriber("https://g.test/v1", "k", ["m"], transport=httpx.MockTransport(down))
    with pytest.raises(SttError) as error:
        stt.transcribe(b"x")
    assert error.value.code == "unreachable"


# ---- microphone --------------------------------------------------------------


def tone(amplitude, blocks=1):
    samples = array("h", [int(amplitude * math.sin(i / 3)) for i in range(1600)])
    return [samples.tobytes()] * blocks


def silence(blocks=1):
    return [bytes(3200)] * blocks


def fake_source(blocks, delay=0.0):
    @contextmanager
    def factory():
        def generate():
            for block in blocks:
                if delay:
                    time.sleep(delay)
                yield block

        yield generate()

    return factory


def test_rms_level_and_wav():
    assert rms(bytes(3200)) == 0.0
    loud = tone(8000)[0]
    assert 5000 < rms(loud) < 6000
    assert level_of(0) == 0.0 and 0 < level_of(rms(loud)) <= 1.0
    wav = to_wav(loud)
    assert wav[:4] == b"RIFF" and struct.unpack("<I", wav[24:28])[0] == 16000


def test_recorder_stops_after_silence_following_speech():
    blocks = silence(3) + tone(6000, 8) + silence(20) + tone(6000, 50)
    levels = []
    recording = Recorder(fake_source(blocks), silence_seconds=1.0).record(levels.append)
    assert recording.heard_speech and not recording.cancelled
    assert recording.seconds == pytest.approx(2.1, abs=0.15)  # 0.3 + 0.8 + 1.0
    assert len(levels) == 21 and max(levels) > 0.5


def test_recorder_gives_up_when_nothing_is_said():
    recording = Recorder(fake_source(silence(200)), no_speech_seconds=2).record()
    assert not recording.heard_speech and recording.seconds == pytest.approx(2.0)


def test_recorder_finish_and_cancel_from_another_thread():
    recorder = Recorder(fake_source(tone(6000, 300), delay=0.005))
    threading.Timer(0.15, recorder.finish).start()
    recording = recorder.record()
    assert recording.heard_speech and recording.seconds < 20  # stopped long before the end

    recorder = Recorder(fake_source(tone(6000, 300), delay=0.005))
    threading.Timer(0.15, recorder.cancel).start()
    recording = recorder.record()
    assert recording.cancelled and recording.pcm == b""


def test_recorder_respects_max_seconds_and_rejects_parallel_use():
    recorder = Recorder(fake_source(tone(6000, 400)), max_seconds=3)
    assert recorder.record().seconds == pytest.approx(3.0)


# ---- speaking ------------------------------------------------------------------


class FakeSynth:
    name = "fake"

    def __init__(self, fail_on=None):
        self.texts = []
        self.fail_on = fail_on

    def available(self):
        return True

    def synth(self, text, gender, out_dir):
        if self.fail_on and self.fail_on in text:
            raise TtsError("boom")
        self.texts.append((text, gender))
        path = Path(out_dir) / f"{len(self.texts)}.mp3"
        path.write_bytes(b"audio")
        return Audio(path, "mp3")


class FakePlayer:
    def __init__(self, seconds=0.0):
        self.played = []
        self.seconds = seconds

    def available(self):
        return True

    def play(self, path, kind, cancel):
        self.played.append(path.read_bytes())
        cancel.wait(self.seconds)
        return True


def test_speaker_says_every_chunk_in_order_and_reports_state(tmp_path):
    states = []
    synth, player = FakeSynth(), FakePlayer()
    speaker = Speaker(synth, player, tmp_path, on_state=states.append)
    assert speaker.say("**Namaste!** Quantum computing ek naya tareeka hai. " * 5, "female")
    speaker.wait(5)
    first = synth.texts[0][0]
    assert first.startswith("Namaste!") and len(first) <= 90
    assert all(g == "female" for _, g in synth.texts) and len(player.played) == len(synth.texts)
    assert states == ["speaking", "idle"]
    assert list(tmp_path.iterdir()) == []  # audio files are cleaned up


def test_speaker_stop_cuts_speech_short(tmp_path):
    states = []
    player = FakePlayer(seconds=5)
    speaker = Speaker(FakeSynth(), player, tmp_path, on_state=states.append)
    speaker.say("Ek. Do. Teen. Char. Paanch.")
    time.sleep(0.2)
    started = time.monotonic()
    speaker.stop()
    assert time.monotonic() - started < 2 and not speaker.speaking
    assert len(player.played) == 1 and states == ["speaking"]


def test_speaker_reports_synth_errors_and_skips_empty_text(tmp_path):
    errors = []
    speaker = Speaker(FakeSynth(fail_on="Do"), FakePlayer(), tmp_path, on_error=errors.append)
    speaker.say("Ek baat. Do baatein hain yahan par aur kuch nahi.")
    speaker.wait(5)
    assert errors == ["boom"]
    assert not speaker.say("```code only```")


def test_chain_synthesizer_falls_back(tmp_path):
    class Broken(FakeSynth):
        name = "broken"

        def synth(self, text, gender, out_dir):
            raise TtsError("offline")

    good = FakeSynth()
    chain = ChainSynthesizer([Broken(), good])
    assert chain.synth("hello", "male", tmp_path).kind == "mp3" and chain.last_used == "fake"
    with pytest.raises(TtsError):
        ChainSynthesizer([Broken()]).synth("hello", "male", tmp_path)


def test_sapi_synthesizer_calls_powershell_without_a_window(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        Path(args[8]).write_bytes(b"RIFF" + bytes(200))
        assert Path(args[7]).read_text(encoding="utf-8") == "नमस्ते दोस्त"
        return subprocess.CompletedProcess(args, 0)

    sapi = SapiSynthesizer(tmp_path / "scripts", platform="win32", run=run)
    audio = sapi.synth("नमस्ते दोस्त", "female", tmp_path)
    args, kwargs = calls[0]
    assert args[0] == "powershell" and args[9:] == ["hi-IN", "Female"]
    assert kwargs["creationflags"] == 0x08000000 and audio.kind == "wav"
    assert not Path(args[7]).exists()  # the text file is removed
    assert not SapiSynthesizer(tmp_path, platform="linux").available()


# ---- the whole voice turn over the WebSocket ----------------------------------------


def voice_runtime(settings, registry, tmp_path, blocks, stt_reply, script, synth=None, player=None):
    seen = []
    transport = stt_transport([(200, {"text": stt_reply})], seen)
    runtime = CoreRuntime(
        settings,
        token=TOKEN,
        home=tmp_path,
        secrets=MemoryStore(),
        llm=ScriptedLLM(script),
        registry=registry,
        env={"GROQ_API_KEY": "gk"},
        voice=VoiceEngine(
            settings.defaults["voice"],
            settings.models["speech"],
            settings.models["providers"],
            lambda name: "gk" if name == "groq" else "",
            home=tmp_path,
            synthesizer=synth or FakeSynth(),
            player=player or FakePlayer(),
            mic_source=fake_source(blocks),
            transport=transport,
        ),
    )
    return runtime, seen


def read_until(ws, kind, limit=200):
    events = []
    for _ in range(limit):
        event = json.loads(ws.receive_text())
        events.append(event)
        if event["type"] == kind:
            return events
    raise AssertionError(f"no {kind} in {[e['type'] for e in events]}")


def test_push_to_talk_runs_a_turn_and_speaks_the_reply(settings, registry, spawned, tmp_path):
    synth, player = FakeSynth(), FakePlayer()
    runtime, seen = voice_runtime(
        settings,
        registry,
        tmp_path,
        silence(3) + tone(6000, 6) + silence(15),
        "क्रोम खोलो",
        [[{"name": "open_app", "arguments": {"name": "chrome"}}], "Chrome khol diya!"],
        synth,
        player,
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        hello = read_until(ws, "hello")[-1]
        assert hello["capabilities"]["voice"]["input"] is True
        ws.send_text(json.dumps({"v": 1, "type": "listen_start"}))
        events = read_until(ws, "assistant_message")
        while not (events[-1]["type"] == "state_change" and events[-1]["state"] == "idle"):
            events += read_until(ws, "state_change")
    kinds = [e["type"] for e in events]
    assert kinds.index("audio_level") < kinds.index("transcript_final") < kinds.index("tool_result")
    transcript = next(e for e in events if e["type"] == "transcript_final")
    assert transcript["text"] == "क्रोम खोलो" and transcript["language"] == "hi"
    assert spawned == [("exe", "chrome")]
    states = [e["state"] for e in events if e["type"] == "state_change"]
    assert states[:2] == ["listening", "thinking"] and states[-2:] == ["speaking", "idle"]
    assert "idle" not in states[:-1]  # the orb goes straight from the reply to speaking
    assert synth.texts == [("Chrome khol diya!", "male")] and len(player.played) == 1
    assert b"RIFF" in seen[0].content


def test_listening_without_speech_sends_a_notice(settings, registry, tmp_path):
    runtime, seen = voice_runtime(settings, registry, tmp_path, silence(100), "ignored", [])
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        ws.send_text(json.dumps({"v": 1, "type": "listen_start"}))
        events = read_until(ws, "notice")
        events += read_until(ws, "state_change")
    assert "sunai nahi" in events[-2]["text"] and events[-1]["state"] == "idle"
    assert seen == []  # nothing was sent to the speech service


def test_voice_input_needs_a_key(settings, registry, tmp_path):
    runtime = CoreRuntime(
        settings,
        token=TOKEN,
        home=tmp_path,
        secrets=MemoryStore(),
        llm=ScriptedLLM([]),
        registry=registry,
        env={},
        voice=VoiceEngine(
            settings.defaults["voice"],
            settings.models["speech"],
            settings.models["providers"],
            lambda name: "",
            home=tmp_path,
            synthesizer=FakeSynth(),
            player=FakePlayer(),
            mic_source=fake_source(silence(1)),
        ),
    )
    client = TestClient(create_app(runtime))
    assert client.get("/v1/voice", headers=AUTH).json()["input_reason"] == "needs a Groq API key"
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        assert read_until(ws, "hello")[-1]["capabilities"]["voice"]["input"] is False
        ws.send_text(json.dumps({"v": 1, "type": "listen_start"}))
        error = read_until(ws, "error")[-1]
    assert error["code"] == "voice_unavailable"


def test_speak_event_replays_text_and_muted_replies_are_not_spoken(settings, registry, tmp_path):
    synth = FakeSynth()
    runtime, _ = voice_runtime(settings, registry, tmp_path, [], "", ["Theek hai."], synth)
    runtime.update_settings({"speak_replies": False, "voice_gender": "female"})
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        ws.send_text(json.dumps({"v": 1, "type": "user_message", "text": "hi"}))
        read_until(ws, "assistant_message")
        assert synth.texts == []
        ws.send_text(json.dumps({"v": 1, "type": "speak", "text": "Phir se suno."}))
        read_until(ws, "state_change")
        read_until(ws, "state_change")
    assert synth.texts == [("Phir se suno.", "female")]


def test_global_shortcut_toggles_listening_for_the_open_window(
    settings, registry, spawned, tmp_path
):
    runtime, _ = voice_runtime(
        settings,
        registry,
        tmp_path,
        silence(3) + tone(6000, 6) + silence(15),
        "notepad kholo",
        [[{"name": "open_app", "arguments": {"name": "notepad"}}], "Notepad khul gaya."],
    )
    runtime.hotkey_pressed()  # no window connected: nothing happens
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        assert runtime.active_session is not None
        runtime.hotkey_pressed()
        events = read_until(ws, "assistant_message")
    assert any(e["type"] == "transcript_final" for e in events)
    assert spawned == [("exe", "notepad")]
    assert runtime.active_session is None  # the window closed


def test_start_hotkey_is_windows_only():
    from rishu_core.voice.hotkey import start_hotkey

    if sys.platform != "win32":
        assert start_hotkey(lambda: None) is False
