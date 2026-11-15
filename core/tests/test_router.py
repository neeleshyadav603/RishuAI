import json

import httpx
import pytest

from rishu_core.llm import AllProvidersFailed, LLMRouter

MODELS_CFG = {
    "order": ["groq", "gemini", "ollama"],
    "providers": {
        "groq": {
            "base_url": "https://groq.test/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "models": {
                "fast": ["g-fast"],
                "smart": ["g-old", "g-smart"],
                "coder": [],
                "vision": [],
            },
        },
        "gemini": {
            "base_url": "https://gemini.test/v1beta/openai",
            "api_key_env": "GEMINI_API_KEY",
            "models": {
                "fast": ["gem-fast"],
                "smart": ["gem-smart"],
                "coder": [],
                "vision": ["gem-v"],
            },
        },
        "ollama": {
            "base_url": "http://ollama.test/v1",
            "local": True,
            "models": {"fast": [], "smart": [], "coder": [], "vision": []},
        },
    },
}
ENV = {"GROQ_API_KEY": "k1", "GEMINI_API_KEY": "k2"}


def reply(model, text="ok", tool_calls=None):
    message = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return httpx.Response(200, json={"model": model, "choices": [{"message": message}]})


class FakeProviders:
    """One transport that plays all providers; behaviour is set per test."""

    def __init__(self):
        self.models = {
            "groq.test": ["g-fast", "g-smart"],
            "gemini.test": ["models/gem-fast", "models/gem-smart", "models/gem-v"],
            "ollama.test": ["llama-local"],
        }
        self.chat_status = {}  # host -> status code to return instead of a reply
        self.down = set()
        self.seen = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host in self.down:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in self.models[host]]})
        body = json.loads(request.content)
        self.seen.append((host, body["model"], request.headers.get("authorization")))
        if host in self.chat_status:
            return httpx.Response(self.chat_status[host], json={"error": {"message": "nope"}})
        return reply(body["model"], f"hello from {host}")


@pytest.fixture
def fake():
    return FakeProviders()


def make_router(fake, env=ENV, **kwargs):
    return LLMRouter.from_settings(
        MODELS_CFG, env=env, transport=httpx.MockTransport(fake), **kwargs
    )


def test_uses_first_provider_and_skips_models_that_no_longer_exist(fake):
    response = make_router(fake).chat("smart", [{"role": "user", "content": "hi"}])
    assert response.provider == "groq"
    # "g-old" is configured but missing from /models, so it is never tried.
    assert fake.seen == [("groq.test", "g-smart", "Bearer k1")]
    assert response.note is None


def test_quota_429_falls_back_to_next_provider_with_note(fake):
    fake.chat_status["groq.test"] = 429
    router = make_router(fake)
    response = router.chat("fast", [{"role": "user", "content": "hi"}])
    assert response.provider == "gemini"
    assert "429" in response.note
    # While groq cools down it is not contacted again.
    fake.seen.clear()
    router.chat("fast", [{"role": "user", "content": "again"}])
    assert [host for host, _, _ in fake.seen] == ["gemini.test"]


def test_cooldown_expires(fake):
    now = [0.0]
    fake.chat_status["groq.test"] = 429
    router = make_router(fake, clock=lambda: now[0], cooldown_seconds=60)
    router.chat("fast", [{"role": "user", "content": "hi"}])
    del fake.chat_status["groq.test"]
    now[0] = 61.0
    assert router.chat("fast", [{"role": "user", "content": "hi"}]).provider == "groq"


def test_falls_back_to_local_model_when_cloud_is_down(fake):
    fake.down.update({"groq.test", "gemini.test"})
    response = make_router(fake).chat("smart", [{"role": "user", "content": "hi"}])
    assert response.provider == "ollama"
    assert fake.seen[-1][1] == "llama-local"  # discovered, not configured
    assert fake.seen[-1][2] is None  # no API key sent to the local server


def test_all_providers_failed_lists_reasons(fake):
    fake.down.update({"groq.test", "gemini.test", "ollama.test"})
    with pytest.raises(AllProvidersFailed) as error:
        make_router(fake).chat("smart", [{"role": "user", "content": "hi"}])
    assert len(error.value.reasons) == 3
    assert any("local model server not reachable" in r for r in error.value.reasons)


def test_providers_without_key_are_skipped(fake):
    router = make_router(fake, env={"GEMINI_API_KEY": "k2"})
    assert [p.name for p in router.providers] == ["gemini", "ollama"]
    assert router.has_cloud_provider()


def test_vision_role_never_borrows_a_text_model(fake):
    response = make_router(fake).chat("vision", [{"role": "user", "content": "look"}])
    assert (response.provider, fake.seen[-1][1]) == ("gemini", "gem-v")


def test_coder_role_borrows_smart_model(fake):
    make_router(fake).chat("coder", [{"role": "user", "content": "code"}])
    assert fake.seen[-1][:2] == ("groq.test", "g-smart")


def test_tool_calls_are_parsed_and_bad_json_is_flagged(fake):
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "g-fast"}]})
        return reply(
            "g-fast",
            "",
            [
                {"id": "a", "function": {"name": "open_app", "arguments": '{"name": "chrome"}'}},
                {"id": "b", "function": {"name": "open_app", "arguments": "{not json"}},
            ],
        )

    router = LLMRouter.from_settings(
        MODELS_CFG, env={"GROQ_API_KEY": "k"}, transport=httpx.MockTransport(handler)
    )
    response = router.chat("fast", [{"role": "user", "content": "x"}], tools=[{"type": "function"}])
    good, bad = response.tool_calls
    assert good.arguments == {"name": "chrome"} and good.parse_error is None
    assert bad.arguments == {} and bad.parse_error
    assert response.to_message()["tool_calls"][0]["function"]["name"] == "open_app"
