"""End-to-end check against a real model server (Ollama on CI).

Runs the real router, streaming client and agent loop through the local
WebSocket server, exactly as the app does. Usage:

    python scripts/llm_e2e.py            # needs Ollama on 127.0.0.1:11434
"""

from __future__ import annotations

import json
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

from rishu_core.api.runtime import CoreRuntime
from rishu_core.api.serve import HOST, bind_socket, build_server
from rishu_core.config import load_settings
from rishu_core.security import MemoryStore
from rishu_core.voice import VoiceEngine
from rishu_core.voice.player import NullPlayer
from websockets.sync.client import connect


def run_turn(ws, text: str, timeout: float = 240) -> list[dict]:
    ws.send(json.dumps({"v": 1, "type": "user_message", "text": text}))
    events: list[dict] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = json.loads(ws.recv(timeout=timeout))
        events.append(event)
        if event["type"] == "state_change" and event["state"] == "idle" and any(
            e["type"] == "assistant_message" for e in events
        ):
            return events
    raise TimeoutError(text)


def main() -> int:
    settings = load_settings()
    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as home:
        runtime = CoreRuntime(
            settings,
            token=token,
            home=Path(home),
            secrets=MemoryStore(),
            env={},  # no cloud keys: the router must use the local Ollama server
            voice=VoiceEngine(
                settings.defaults.get("voice", {}),
                settings.models.get("speech", {}),
                settings.models.get("providers", {}),
                lambda name: "",
                home=Path(home),
                player=NullPlayer(),
            ),
        )
        sock = bind_socket(0)
        server = build_server(runtime)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        ok = True
        try:
            url = f"ws://{HOST}:{sock.getsockname()[1]}/ws"
            with connect(url, additional_headers={"Authorization": f"Bearer {token}"}, open_timeout=30) as ws:
                hello = json.loads(ws.recv(timeout=30))
                print("providers:", [(p["name"], p["configured"]) for p in hello["providers"]])

                events = run_turn(ws, "Say hello to Neelesh in one short sentence.")
                tokens = [e for e in events if e["type"] == "assistant_token"]
                reply = [e for e in events if e["type"] == "assistant_message"][-1]
                offline = any(e.get("state") == "offline" for e in events if e["type"] == "state_change")
                print(f"plain turn: {len(tokens)} streamed tokens, provider={reply.get('provider')}, offline={offline}")
                print("  reply:", reply["text"][:200])
                if offline or not tokens or not reply["text"].strip():
                    ok = False

                events = run_turn(ws, "What is the exact current time? Use the get_time tool.")
                tools = [e for e in events if e["type"] == "tool_result"]
                reply = [e for e in events if e["type"] == "assistant_message"][-1]
                print(f"tool turn: tools={[t['tool'] for t in tools]}")
                print("  reply:", reply["text"][:200])
                # Small CI models do not always call tools; report, do not fail.
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    print("llm e2e ok" if ok else "llm e2e FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
