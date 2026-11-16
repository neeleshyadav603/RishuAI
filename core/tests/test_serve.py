"""The real server process: start it like the app does, talk to it, let it exit."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from websockets.sync.client import connect

TOKEN = "serve-test-token-0123456789"
CORE = Path(__file__).resolve().parents[1]


def start_core(tmp_path, token=TOKEN, extra=()):
    env = {**os.environ, "RISHU_HOME": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        env.pop(name, None)
    if token is None:
        env.pop("RISHU_TOKEN", None)
    else:
        env["RISHU_TOKEN"] = token
    return subprocess.Popen(
        [sys.executable, "-m", "rishu_core", "--serve", "--exit-with-parent", *extra],
        cwd=CORE,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def read_ready(process):
    line = process.stdout.readline().decode("utf-8")
    assert line.startswith("RISHU_READY "), line + process.stderr.read().decode("utf-8", "replace")
    return json.loads(line.removeprefix("RISHU_READY "))


def test_serve_round_trip_and_exit_with_parent(tmp_path):
    process = start_core(tmp_path)
    try:
        ready = read_ready(process)
        assert ready["protocol"] == 1 and "token" not in ready
        base = f"127.0.0.1:{ready['port']}"
        assert httpx.get(f"http://{base}/health", timeout=10).json()["ok"] is True
        assert httpx.get(f"http://{base}/v1/settings", timeout=10).status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with connect(f"ws://{base}/ws", additional_headers=headers, open_timeout=20) as ws:
            assert json.loads(ws.recv(timeout=20))["type"] == "hello"
            # No API key in this environment: the offline fallback answers.
            ws.send(json.dumps({"v": 1, "type": "user_message", "text": "time kya hua hai"}))
            while True:
                event = json.loads(ws.recv(timeout=20))
                if event["type"] == "assistant_message":
                    assert event["text"].startswith("(Offline mode)")
                    break
        # The app going away closes stdin; the core must stop by itself.
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.stderr.close()


def test_serve_refuses_a_short_token(tmp_path):
    process = start_core(tmp_path, token="short")
    try:
        assert process.wait(timeout=30) == 2
    finally:
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


def test_serve_started_by_hand_prints_a_generated_token(tmp_path):
    process = start_core(tmp_path, token=None)
    try:
        ready = read_ready(process)
        assert len(ready["token"]) >= 32
        headers = {"Authorization": f"Bearer {ready['token']}"}
        url = f"http://127.0.0.1:{ready['port']}/v1/settings"
        assert httpx.get(url, headers=headers, timeout=10).status_code == 200
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.stderr.close()
