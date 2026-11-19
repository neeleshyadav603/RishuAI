"""Token streaming: the provider client, the router fallback and the agent loop."""

import json

import httpx
import pytest

from rishu_core.agent import Agent, build_system_prompt
from rishu_core.llm import LLMRouter, ModelFailed, ProviderUnavailable, TokenStream
from rishu_core.llm.mock import ScriptedLLM
from rishu_core.llm.openai_compat import OpenAICompatClient
from rishu_core.permissions import PermissionEngine


def sse(*chunks, done=True):
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def delta(**fields):
    return {"model": "m-1", "choices": [{"delta": fields}]}


def collect():
    tokens, resets = [], []
    return TokenStream(tokens.append, lambda: resets.append(len(tokens))), tokens, resets


def test_stream_text_arrives_piece_by_piece():
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            content=sse(
                delta(role="assistant"), delta(content="Namaste "), delta(content="Neelesh")
            ),
            headers={"content-type": "text/event-stream"},
        )

    client = OpenAICompatClient(
        "groq", "https://x.test/v1", "k", transport=httpx.MockTransport(handler)
    )
    stream, tokens, resets = collect()
    response = client.chat("m-1", [{"role": "user", "content": "hi"}], stream=stream)
    assert tokens == ["Namaste ", "Neelesh"]
    assert response.content == "Namaste Neelesh"
    assert response.tool_calls == [] and resets == []


def test_stream_tool_call_is_assembled_from_pieces():
    chunks = [
        delta(
            tool_calls=[
                {"index": 0, "id": "call_a", "function": {"name": "open_app", "arguments": ""}}
            ]
        ),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"na'}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": 'me": "chrome"}'}}]),
        # A second call delivered whole and without an index (as Gemini does).
        delta(
            tool_calls=[{}, {"id": "call_b", "function": {"name": "get_time", "arguments": "{}"}}]
        ),
    ]
    client = OpenAICompatClient(
        "groq",
        "https://x.test/v1",
        "k",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=sse(*chunks))),
    )
    stream, tokens, _ = collect()
    response = client.chat("m-1", [], tools=[{"type": "function"}], stream=stream)
    assert tokens == []
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("call_a", "open_app", {"name": "chrome"}),
        ("call_b", "get_time", {}),
    ]


def test_stream_http_error_maps_like_a_normal_call():
    client = OpenAICompatClient(
        "groq",
        "https://x.test/v1",
        "k",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="down")),
    )
    stream, _, _ = collect()
    with pytest.raises(ProviderUnavailable):
        client.chat("m-1", [], stream=stream)


def test_stream_error_event_midway_raises():
    body = sse(delta(content="Half "), {"error": {"message": "boom"}}, done=False)
    client = OpenAICompatClient(
        "groq",
        "https://x.test/v1",
        "k",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
    )
    stream, tokens, _ = collect()
    with pytest.raises(ModelFailed):
        client.chat("m-1", [], stream=stream)
    assert tokens == ["Half "]


def test_router_discards_partial_text_before_falling_back():
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "a-1"}, {"id": "b-1"}]})
        if request.url.host == "a.test":
            return httpx.Response(
                200, content=sse(delta(content="Broken "), {"error": {"message": "x"}}, done=False)
            )
        return httpx.Response(200, content=sse(delta(content="Sahi "), delta(content="jawab")))

    config = {
        "order": ["a", "b"],
        "providers": {
            "a": {
                "base_url": "https://a.test/v1",
                "api_key_env": "A",
                "models": {"smart": ["a-1"]},
            },
            "b": {
                "base_url": "https://b.test/v1",
                "api_key_env": "B",
                "models": {"smart": ["b-1"]},
            },
        },
    }
    router = LLMRouter.from_settings(
        config, env={"A": "ka", "B": "kb"}, transport=httpx.MockTransport(handler)
    )
    stream, tokens, resets = collect()
    response = router.chat("smart", [{"role": "user", "content": "hi"}], stream=stream)
    assert response.content == "Sahi jawab" and response.provider == "b"
    assert tokens == ["Broken ", "Sahi ", "jawab"]
    assert resets == [1]  # the reset came after the broken piece, before the good ones
    assert response.note.startswith("Using b")


def make_agent(settings, registry, script, **kwargs):
    events = []
    agent = Agent(
        ScriptedLLM(script),
        registry,
        PermissionEngine(settings.policy),
        system_prompt=build_system_prompt(settings),
        on_event=events.append,
        streaming=True,
        **kwargs,
    )
    return agent, events


def test_agent_streams_tokens_then_the_full_message(settings, registry):
    agent, events = make_agent(settings, registry, ["Chrome khol diya, Neelesh."])
    result = agent.run_turn("hello")
    tokens = [e["text"] for e in events if e["type"] == "assistant_token"]
    assert "".join(tokens) == "Chrome khol diya, Neelesh." and len(tokens) == 4
    kinds = [e["type"] for e in events]
    assert kinds.index("assistant_token") < kinds.index("assistant_message")
    assert result.reply == "Chrome khol diya, Neelesh."


def test_agent_without_streaming_sends_no_tokens(settings, registry):
    agent, events = make_agent(settings, registry, ["Namaste."])
    agent.streaming = False
    agent.run_turn("hello")
    assert not [e for e in events if e["type"] == "assistant_token"]


def test_stop_during_a_streamed_reply_ends_the_turn(settings, registry):
    agent, events = make_agent(settings, registry, ["one two three four five"])

    def stop_after_two(event):
        events.append(event)
        if [e["type"] for e in events].count("assistant_token") == 2:
            agent.stop()

    agent.on_event = stop_after_two
    result = agent.run_turn("count")
    assert result.reply == "Theek hai, ruk gaya."
    tokens = [e for e in events if e["type"] == "assistant_token"]
    assert [t["text"] for t in tokens[:2]] == ["one", " two"]
    assert tokens[-1].get("reset") is True  # the half reply is withdrawn
    assert agent.history[-1] == {"role": "assistant", "content": "Theek hai, ruk gaya."}
