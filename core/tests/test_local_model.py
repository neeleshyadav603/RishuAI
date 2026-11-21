"""Rishu's offline model: download with checks, start on demand, router fallback."""

import hashlib
import json

import httpx

from rishu_core.llm import LLMRouter
from rishu_core.llm.local import LocalModel

CFG = {
    "default": "small",
    "ctx_size": 2048,
    "choices": {
        "small": {
            "label": "Chhota",
            "repo": "ggml-org/Qwen3-0.6B-GGUF",
            "file_suffix": "Q4_K_M.gguf",
            "size_mb": 1,
        },
        "better": {
            "label": "Behtar",
            "repo": "ggml-org/Qwen3-1.7B-GGUF",
            "file_suffix": "Q4_K_M.gguf",
            "size_mb": 2,
        },
    },
}
BLOB = b"GGUF" + bytes(range(256)) * 40


def hub(blob=BLOB, sha=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "/api/models/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "siblings": [
                        {"rfilename": "Qwen3-0.6B-Q8_0.gguf"},
                        {
                            "rfilename": "Qwen3-0.6B-Q4_K_M.gguf",
                            "lfs": {
                                "size": len(blob),
                                "sha256": sha or hashlib.sha256(blob).hexdigest(),
                            },
                        },
                    ]
                },
            )
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, content=blob)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


class FakeProcess:
    def __init__(self, args, **kwargs):
        self.args, self.stopped = args, False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0


def test_download_checks_the_file_and_reports_progress(tmp_path):
    http, calls = hub()
    model = LocalModel(
        tmp_path, CFG, server=lambda: tmp_path / "llama-server.exe", http=http, sleep=lambda s: None
    )
    events = []
    model.listeners.append(events.append)
    assert model.status()["downloaded"] is False and model.status()["engine"] is True
    assert model.download()
    path = model.model_path()
    assert path.name == "Qwen3-0.6B-Q4_K_M.gguf" and path.read_bytes() == BLOB
    assert any(
        c.endswith("/ggml-org/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf") for c in calls
    )
    assert events[-1]["downloaded"] is True and events[-1]["progress"] is None
    model.choose("better")
    assert model.model_path() is None  # the other model is not downloaded


def test_a_damaged_download_is_thrown_away(tmp_path):
    http, _ = hub(sha="0" * 64)
    model = LocalModel(tmp_path, CFG, server=lambda: None, http=http, sleep=lambda s: None)
    assert not model.download()
    assert "damaged" in model.error and model.model_path() is None
    assert not list((tmp_path / "models").glob("*.part"))


def test_server_starts_on_first_use_and_stops(tmp_path):
    http, _ = hub()
    spawned = []

    def spawn(args, **kwargs):
        spawned.append(FakeProcess(args))
        return spawned[-1]

    model = LocalModel(
        tmp_path,
        CFG,
        server=lambda: tmp_path / "llama-server.exe",
        http=http,
        spawn=spawn,
        sleep=lambda s: None,
    )
    assert model.ensure() is None  # nothing downloaded yet: not available, nothing started
    model.download()
    url = model.ensure()
    assert url.startswith("http://127.0.0.1:") and url.endswith("/v1")
    args = spawned[0].args
    assert (
        "--jinja" in args and args[args.index("--ctx-size") + 1] == "2048" and "127.0.0.1" in args
    )
    assert model.ensure() == url and len(spawned) == 1  # reused
    model.stop()
    assert spawned[0].stopped and model.status()["running"] is False


def test_router_falls_back_to_the_offline_model_with_fewer_tools():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.groq.com":
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen3-0.6b"}]})
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "Theek hai"}}]}
        )

    cfg = {
        "order": ["groq", "rishu_local"],
        "providers": {
            "groq": {
                "base_url": "https://api.groq.com/openai/v1",
                "api_key_env": "K",
                "models": {"fast": ["m1"]},
            },
            "rishu_local": {
                "base_url": "http://127.0.0.1:1/v1",
                "local": True,
                "managed": True,
                "tools_allow": ["get_time"],
                "models": {},
            },
        },
    }
    tools = [
        {"type": "function", "function": {"name": n, "parameters": {}}}
        for n in ("get_time", "sheet_fill")
    ]
    transport = httpx.MockTransport(handler)
    router = LLMRouter.from_settings(
        cfg,
        env={"K": "x"},
        transport=transport,
        managed={"rishu_local": lambda: "http://127.0.0.1:5555/v1"},
    )
    reply = router.chat("fast", [{"role": "user", "content": "time?"}], tools)
    assert reply.provider == "rishu_local" and reply.content == "Theek hai"
    assert [t["function"]["name"] for t in seen[0]["tools"]] == ["get_time"]
    # Without the managed hook (tests, other platforms) the provider is simply absent.
    assert [
        p.name for p in LLMRouter.from_settings(cfg, env={"K": "x"}, transport=transport).providers
    ] == ["groq"]


def test_bundled_model_is_found_and_never_deleted(tmp_path):
    server = tmp_path / "local-llm" / "llama-server.exe"
    (tmp_path / "local-llm" / "models").mkdir(parents=True)
    server.write_text("x")
    bundled = tmp_path / "local-llm" / "models" / "Qwen3-0.6B-Q4_K_M.gguf"
    bundled.write_bytes(BLOB)
    model = LocalModel(tmp_path / "home", CFG, server=lambda: server, sleep=lambda s: None)
    status = model.status()
    assert status["downloaded"] is True and status["bundled"] is True
    model.delete()
    assert bundled.exists()


def test_compact_prompt_is_used_only_for_small_local_models():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen3-0.6b"}]})
        seen.append(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        )

    cfg = {
        "order": ["rishu_local"],
        "providers": {
            "rishu_local": {
                "base_url": "http://127.0.0.1:1/v1",
                "local": True,
                "managed": True,
                "compact_prompt": True,
                "models": {},
            }
        },
    }
    router = LLMRouter.from_settings(
        cfg,
        env={},
        transport=httpx.MockTransport(handler),
        managed={"rishu_local": lambda: "http://127.0.0.1:5/v1"},
    )
    router.compact = lambda msgs: [{**msgs[0], "content": "SHORT"}, *msgs[1:]]
    router.chat(
        "fast",
        [{"role": "system", "content": "LONG RULES"}, {"role": "user", "content": "hi"}],
        None,
    )
    assert seen == ["SHORT"]


def test_runtime_swaps_the_long_rules_for_the_short_ones(settings, registry, tmp_path):
    from test_api import make_runtime

    from rishu_core.agent.factory import build_system_prompt
    from rishu_core.config import read_prompt

    runtime = make_runtime(settings, registry, tmp_path, script=[])
    prompt = build_system_prompt(settings)
    compact = runtime._compact_messages(
        [{"role": "system", "content": prompt}, {"role": "user", "content": "x"}]
    )
    short = compact[0]["content"]
    assert read_prompt("system_rules_compact") in short and read_prompt("system_rules") not in short
    assert len(short) < len(prompt) * 0.75


def test_the_preferred_quantisation_that_the_repo_has_is_chosen():
    from rishu_core.llm.local import pick_file

    spec = {"file_suffix": "Q4_K_M.gguf"}
    files = ["Qwen3-0.6B-f16.gguf", "Qwen3-0.6B-Q8_0.gguf", "README.md"]
    assert pick_file(files, spec) == "Qwen3-0.6B-Q8_0.gguf"
    assert pick_file([*files, "qwen3-0.6b-q4_k_m.gguf"], spec) == "qwen3-0.6b-q4_k_m.gguf"
    assert pick_file(["mmproj-Q8_0.gguf", "Qwen3-0.6B-f16.gguf"], spec) is None


def test_a_repo_without_the_first_choice_still_downloads(tmp_path):
    blob = b"GGUF" + b"x" * 500

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/models/" in request.url.path:
            files = [
                {"rfilename": "Qwen3-0.6B-f16.gguf"},
                {
                    "rfilename": "Qwen3-0.6B-Q8_0.gguf",
                    "lfs": {"size": len(blob), "sha256": hashlib.sha256(blob).hexdigest()},
                },
            ]
            return httpx.Response(200, json={"siblings": files})
        return httpx.Response(200, content=blob)

    model = LocalModel(
        tmp_path,
        CFG,
        server=lambda: tmp_path / "llama-server.exe",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert model.download() is True
    assert model.model_path().name == "Qwen3-0.6B-Q8_0.gguf"
