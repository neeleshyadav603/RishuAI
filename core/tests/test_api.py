"""The local API: authentication, a full turn over WebSocket, approvals, STOP, settings."""

import json
import threading
from pathlib import Path

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rishu_core.api import CoreRuntime, create_app
from rishu_core.llm.mock import ScriptedLLM
from rishu_core.permissions import Risk
from rishu_core.security import MemoryStore
from rishu_core.tools import Tool, ToolResult

TOKEN = "test-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PROTOCOL = Path(__file__).resolve().parents[2] / "shared" / "protocol"
VALIDATOR = jsonschema.Draft202012Validator(
    json.loads((PROTOCOL / "events.schema.json").read_text(encoding="utf-8"))
)


def make_runtime(settings, registry, tmp_path, script=None, **kwargs):
    return CoreRuntime(
        settings,
        token=TOKEN,
        home=tmp_path,
        secrets=kwargs.pop("secrets", MemoryStore()),
        llm=ScriptedLLM(script) if script is not None else None,
        registry=registry,
        env=kwargs.pop("env", {}),
        **kwargs,
    )


def add_send_tool(registry, sent, risk=Risk.R2, skill=None):
    registry.register(
        Tool(
            name="send_message",
            description="Send a message to a contact.",
            parameters={
                "type": "object",
                "properties": {"to": {"type": "string"}, "text": {"type": "string"}},
                "required": ["to", "text"],
            },
            risk=risk,
            handler=lambda to, text: sent.append((to, text)) or ToolResult(True, "sent"),
            preview_fn=lambda a: f"Send to {a['to']}: {a['text']}",
            skill=skill,
        )
    )


def say(ws, text):
    ws.send_text(json.dumps({"v": 1, "type": "user_message", "text": text}))


def read_until(ws, kind, limit=60):
    """Collect events up to and including the first of type ``kind``; all must match the schema."""
    events = []
    for _ in range(limit):
        event = json.loads(ws.receive_text())
        VALIDATOR.validate(event)
        events.append(event)
        if event["type"] == kind:
            return events
    raise AssertionError(f"no '{kind}' event within {limit} events: {[e['type'] for e in events]}")


def read_turn(ws):
    """Events of one whole turn (it ends with state idle after the assistant message)."""
    events = read_until(ws, "assistant_message")
    events += read_until(ws, "state_change")
    assert events[-1]["state"] == "idle"
    return events


# ---- authentication ---------------------------------------------------------


def test_health_needs_no_token_and_says_nothing_private(settings, registry, tmp_path):
    client = TestClient(create_app(make_runtime(settings, registry, tmp_path)))
    body = client.get("/health").json()
    assert body["ok"] is True and body["protocol"] == 1
    assert set(body) == {"ok", "name", "version", "protocol"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token-0123456789"},
        {"Authorization": TOKEN},
        {**AUTH, "Origin": "https://evil.example"},
    ],
)
def test_http_api_rejects_missing_token_and_browser_origins(settings, registry, tmp_path, headers):
    client = TestClient(create_app(make_runtime(settings, registry, tmp_path)))
    assert client.get("/v1/settings", headers=headers).status_code in (401, 403)
    assert client.put("/v1/settings", headers=headers, json={"language": "en"}).status_code in (
        401,
        403,
    )


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope-nope-nope-nope"}, {**AUTH, "Origin": "http://x"}]
)
def test_websocket_rejects_missing_token_and_browser_origins(
    settings, registry, tmp_path, headers
):
    client = TestClient(create_app(make_runtime(settings, registry, tmp_path)))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers=headers) as ws:
            ws.receive_text()


def test_short_tokens_are_refused(settings, registry, tmp_path):
    with pytest.raises(ValueError):
        CoreRuntime(settings, token="short", home=tmp_path, registry=registry)


# ---- conversation -----------------------------------------------------------


def test_hello_then_a_streamed_turn_with_a_tool(settings, registry, tmp_path, spawned):
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [[{"name": "open_app", "arguments": {"name": "chrome"}}], "Chrome khol diya."],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        hello = read_until(ws, "hello")[0]
        assert hello["settings"]["autonomy"] == "smart"
        assert [p["name"] for p in hello["providers"]] == ["groq", "gemini", "openrouter", "ollama"]
        assert hello["capabilities"]["step_up"] is False
        say(ws, "Rishu, Chrome kholo")
        events = read_turn(ws)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "state_change" and events[0]["state"] == "thinking"
    assert "tool_progress" in kinds and "tool_result" in kinds
    assert "".join(e["text"] for e in events if e["type"] == "assistant_token") == "Chrome khol diya."
    assert [e for e in events if e["type"] == "assistant_message"][0]["text"] == "Chrome khol diya."
    assert spawned == [("exe", "chrome")]


def test_approval_card_approve_runs_the_action(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent)
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [
            [{"name": "send_message", "arguments": {"to": "Rahul", "text": "10 min late"}}],
            "Bhej diya.",
        ],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "Rahul ko bolo main late hoon")
        proposal = read_until(ws, "tool_call_proposed")[-1]
        assert proposal["decision"] == "confirm" and proposal["risk"] == "R2"
        assert proposal["preview"] == "Send to Rahul: 10 min late"
        assert sent == []  # nothing happens before the user answers
        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "approval_response",
                    "call_id": proposal["call_id"],
                    "approved": True,
                }
            )
        )
        events = read_turn(ws)
    assert sent == [("Rahul", "10 min late")]
    assert events[-2]["text"] == "Bhej diya."


def test_approval_card_deny_does_not_run_the_action(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent)
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [[{"name": "send_message", "arguments": {"to": "Rahul", "text": "hi"}}], "Theek hai."],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "Rahul ko hi bolo")
        proposal = read_until(ws, "tool_call_proposed")[-1]
        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "approval_response",
                    "call_id": proposal["call_id"],
                    "approved": False,
                }
            )
        )
        events = read_turn(ws)
    assert sent == []
    denied = [e for e in events if e["type"] == "tool_progress"]
    assert denied and denied[0]["status"] == "denied"


def test_stop_cancels_a_waiting_approval(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent)
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [[{"name": "send_message", "arguments": {"to": "Rahul", "text": "hi"}}], "unused"],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "Rahul ko hi bolo")
        read_until(ws, "tool_call_proposed")
        ws.send_text(json.dumps({"v": 1, "type": "stop"}))
        events = read_turn(ws)
    assert sent == []
    assert events[-2]["text"] == "Theek hai, ruk gaya."


def test_unanswered_approval_times_out_as_no(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent)
    patched = settings.with_defaults({"server": {"approval_timeout_seconds": 0.05}})
    runtime = make_runtime(
        patched,
        registry,
        tmp_path,
        [[{"name": "send_message", "arguments": {"to": "Rahul", "text": "hi"}}], "Nahi bheja."],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "Rahul ko hi bolo")
        read_turn(ws)
    assert sent == []


def test_r3_is_blocked_until_step_up_exists(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent, risk=Risk.R3)
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [[{"name": "send_message", "arguments": {"to": "Bank", "text": "pay"}}], "Nahi kiya."],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "paise bhejo")
        proposal = read_until(ws, "tool_call_proposed")[-1]
        assert proposal["decision"] == "step_up"
        # Even an explicit "approved" from the app cannot unlock an R3 action.
        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "approval_response",
                    "call_id": proposal["call_id"],
                    "approved": True,
                }
            )
        )
        events = read_turn(ws)
    assert sent == []
    notices = [e["text"] for e in events if e["type"] == "notice"]
    assert any("security check" in text for text in notices)


def test_always_allow_trusts_the_skill_but_never_r3(settings, registry, tmp_path):
    sent = []
    add_send_tool(registry, sent, skill="messaging")
    patched_runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [
            [{"name": "send_message", "arguments": {"to": "Rahul", "text": "one"}}],
            "Pehla bhej diya.",
            [{"name": "send_message", "arguments": {"to": "Rahul", "text": "two"}}],
            "Doosra bhej diya.",
        ],
    )
    patched_runtime.update_settings({"autonomy": "trusted_skills"})
    client = TestClient(create_app(patched_runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "pehla message")
        proposal = read_until(ws, "tool_call_proposed")[-1]
        assert proposal["skill"] == "messaging"
        ws.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "approval_response",
                    "call_id": proposal["call_id"],
                    "approved": True,
                    "always_allow": True,
                }
            )
        )
        read_turn(ws)
        say(ws, "doosra message")
        second = read_turn(ws)
    assert sent == [("Rahul", "one"), ("Rahul", "two")]
    assert "tool_call_proposed" not in [e["type"] for e in second]


def test_bad_frames_get_an_error_and_keep_the_connection(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, ["Namaste."])
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        for frame in (
            "not json",
            json.dumps({"type": "user_message", "text": "no version"}),
            json.dumps({"v": 1, "type": "user_message", "text": "   "}),
            json.dumps({"v": 1, "type": "user_message", "text": "x" * 9000}),
            json.dumps({"v": 1, "type": "approval_response", "call_id": "nope", "approved": True}),
            json.dumps({"v": 1, "type": "launch_missiles"}),
        ):
            ws.send_text(frame)
            assert read_until(ws, "error")[-1]["type"] == "error"
        say(ws, "hello")
        assert read_turn(ws)[-2]["text"] == "Namaste."


def test_second_message_while_busy_is_refused(settings, registry, tmp_path):
    release = threading.Event()
    registry.register(
        Tool(
            name="slow",
            description="Waits.",
            parameters={"type": "object", "properties": {}},
            risk=Risk.R0,
            handler=lambda: ToolResult(True, "done") if release.wait(5) else ToolResult(False, "x"),
        )
    )
    runtime = make_runtime(
        settings, registry, tmp_path, [[{"name": "slow", "arguments": {}}], "Ho gaya."]
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "slow kaam karo")
        read_until(ws, "tool_progress")
        say(ws, "aur ek kaam")
        assert read_until(ws, "error")[-1]["code"] == "busy"
        release.set()
        assert read_turn(ws)[-2]["text"] == "Ho gaya."


def test_no_provider_falls_back_to_offline_commands(settings, registry, tmp_path, spawned):
    runtime = make_runtime(settings, registry, tmp_path)  # no LLM and no keys
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "chrome kholo")
        events = read_turn(ws)
    assert spawned == [("exe", "chrome")]
    assert {"type": "state_change", "state": "offline", "v": 1} in events
    assert events[-2]["text"].startswith("(Offline mode)")


# ---- settings and keys ------------------------------------------------------


def test_settings_round_trip_and_validation(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path)
    client = TestClient(create_app(runtime))
    body = client.get("/v1/settings", headers=AUTH).json()
    assert body["settings"] == {
        "user_name": "",
        "language": "auto",
        "script": "roman",
        "streaming": True,
        "speak_replies": True,
        "autonomy": "smart",
    }
    changed = client.put(
        "/v1/settings", headers=AUTH, json={"user_name": "Neelesh", "autonomy": "ask_always"}
    )
    assert changed.status_code == 200
    assert changed.json()["settings"]["user_name"] == "Neelesh"
    assert runtime.autonomy() == "ask_always"
    for bad in ({"autonomy": "god_mode"}, {"max_auto_risk": 3}, {"language": 7}):
        assert client.put("/v1/settings", headers=AUTH, json=bad).status_code == 422
    assert client.put("/v1/settings", headers=AUTH, content=b"[]").status_code == 422
    assert runtime.autonomy() == "ask_always"


def test_settings_change_applies_to_the_running_session(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, ["Pehla.", "Doosra."])
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "ek")
        read_turn(ws)
        client.put("/v1/settings", headers=AUTH, json={"user_name": "Neelesh", "language": "en"})
        say(ws, "do")
        read_turn(ws)
    first, second = runtime._llm_override.calls
    assert "Neelesh" not in first["messages"][0]["content"]
    assert "The user's name is Neelesh." in second["messages"][0]["content"]
    assert "Reply in English." in second["messages"][0]["content"]
    # The conversation continued: the second request still has the first exchange.
    assert [m["content"] for m in second["messages"][1:]] == ["ek", "Pehla.", "do"]


def provider_transport(valid_key="good-key"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "127.0.0.1":
            raise httpx.ConnectError("nothing is listening")
        if request.headers.get("authorization") != f"Bearer {valid_key}":
            return httpx.Response(401, json={"error": "bad key"})
        return httpx.Response(200, json={"data": [{"id": "m-1"}, {"id": "m-2"}]})

    return httpx.MockTransport(handler)


def test_key_is_tested_saved_and_never_returned(settings, registry, tmp_path):
    secrets = MemoryStore()
    runtime = make_runtime(
        settings, registry, tmp_path, secrets=secrets, transport=provider_transport()
    )
    client = TestClient(create_app(runtime))
    post = lambda body: client.post("/v1/providers/groq/test", headers=AUTH, json=body).json()  # noqa: E731
    assert post({}) == {"ok": False, "code": "no_key"}
    assert post({"api_key": "wrong-key"}) == {"ok": False, "code": "auth"}
    assert post({"api_key": "has space"}) == {"ok": False, "code": "invalid_key"}
    assert post({"api_key": " good-key "}) == {"ok": True, "code": "ok", "models": 2}
    assert secrets.get("GROQ_API_KEY") is None  # testing does not save

    saved = client.put("/v1/providers/groq/key", headers=AUTH, json={"api_key": " good-key\n"})
    assert saved.status_code == 200 and "good-key" not in saved.text
    assert secrets.get("GROQ_API_KEY") == "good-key"
    listed = client.get("/v1/settings", headers=AUTH)
    assert "good-key" not in listed.text
    groq = listed.json()["providers"][0]
    assert groq["configured"] is True and groq["key_source"] == "saved"
    assert post({}) == {"ok": True, "code": "ok", "models": 2}
    assert runtime.llm() is not None and runtime.llm().providers[0].name == "groq"

    assert client.delete("/v1/providers/groq/key", headers=AUTH).status_code == 200
    assert secrets.get("GROQ_API_KEY") is None
    assert client.put("/v1/providers/groq/key", headers=AUTH, json={"api_key": ""}).status_code == 422
    assert client.put("/v1/providers/nope/key", headers=AUTH, json={"api_key": "k"}).status_code == 404
    assert client.put("/v1/providers/ollama/key", headers=AUTH, json={"api_key": "k"}).status_code == 422


def test_local_provider_test_reports_unreachable(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, transport=provider_transport())
    client = TestClient(create_app(runtime))
    result = client.post("/v1/providers/ollama/test", headers=AUTH).json()
    assert result == {"ok": False, "code": "unreachable"}


def test_env_key_counts_as_configured(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, env={"GEMINI_API_KEY": "from-env"})
    by_name = {p["name"]: p for p in runtime.providers()}
    assert by_name["gemini"]["key_source"] == "env" and by_name["gemini"]["configured"]
    assert by_name["groq"]["configured"] is False
    assert runtime.provider_env() == {"GEMINI_API_KEY": "from-env"}


def test_activity_log_endpoint(settings, registry, tmp_path):
    runtime = make_runtime(
        settings,
        registry,
        tmp_path,
        [[{"name": "open_app", "arguments": {"name": "chrome"}}], "Khol diya."],
    )
    client = TestClient(create_app(runtime))
    with client.websocket_connect("/ws", headers=AUTH) as ws:
        read_until(ws, "hello")
        say(ws, "chrome kholo")
        read_turn(ws)
    entries = client.get("/v1/activity", headers=AUTH).json()["entries"]
    assert [(e["tool"], e["risk"], e["approval"], e["ok"]) for e in entries] == [
        ("open_app", "R1", "auto", True)
    ]
