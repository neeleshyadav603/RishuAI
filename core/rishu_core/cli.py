"""Text chat with Rishu in a terminal: ``python -m rishu_core``."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .agent import ApprovalRequest, build_agent
from .config import load_settings
from .permissions import AUTONOMY_MODES


class ConsoleApprover:
    """Asks in the terminal. Step-up needs the security module (Phase 3), so it is refused."""

    def confirm(self, request: ApprovalRequest) -> bool:
        print(f"\n  Rishu wants to: {request.preview}  [{request.risk.label}, {request.reason}]")
        try:
            answer = input("  Allow? (haan/y to approve, anything else to deny): ").strip().lower()
        except EOFError:
            return False
        return answer in ("y", "yes", "haan", "han", "ha", "हाँ", "हां")

    def step_up(self, request: ApprovalRequest) -> bool:
        print(f"\n  Blocked: {request.preview}  [{request.risk.label}]")
        print("  This needs two-factor approval, which arrives with the security module.")
        return False


def _print_event(event: dict[str, Any]) -> None:
    kind = event["type"]
    if kind == "notice":
        print(f"  [note] {event['text']}")
    elif kind == "tool_progress" and event["status"] == "started":
        print(f"  [doing] {event['message']}")
    elif kind == "tool_result" and not event["ok"]:
        print(f"  [failed] {event['summary']}")


def selftest() -> int:
    """Used by the packaged build: prove that config, prompts and optional modules load."""
    import ddgs  # noqa: F401
    import trafilatura  # noqa: F401

    from .agent import build_system_prompt
    from .tools import build_registry
    from .tools.web import extract_text

    settings = load_settings()
    assert "Rishu" in build_system_prompt(settings)
    assert len(build_registry(settings).names()) >= 7
    sample = (
        "<html><body><article>"
        + "<p>Rishu selftest paragraph.</p>" * 20
        + "</article></body></html>"
    )
    assert "Rishu selftest paragraph." in extract_text(sample)
    _selftest_server(settings)
    print("selftest ok")
    return 0


def _selftest_server(settings: Any) -> None:
    """Start the real server on a free port and run one scripted turn over WebSocket."""
    import json
    import secrets
    import tempfile
    import threading
    from pathlib import Path

    from websockets.sync.client import connect

    from .api.runtime import CoreRuntime
    from .api.serve import HOST, bind_socket, build_server
    from .llm.mock import ScriptedLLM
    from .security import MemoryStore

    token = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as home:
        from .voice import VoiceEngine
        from .voice.player import NullPlayer

        runtime = CoreRuntime(
            settings,
            token=token,
            home=Path(home),
            secrets=MemoryStore(),
            llm=ScriptedLLM([[{"name": "get_time", "arguments": {}}], "Selftest reply."]),
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
        try:
            url = f"ws://{HOST}:{sock.getsockname()[1]}/ws"
            headers = {"Authorization": f"Bearer {token}"}
            with connect(url, additional_headers=headers, open_timeout=20) as ws:
                assert json.loads(ws.recv(timeout=20))["type"] == "hello"
                ws.send(json.dumps({"v": 1, "type": "user_message", "text": "time?"}))
                seen = []
                while True:
                    event = json.loads(ws.recv(timeout=20))
                    seen.append(event["type"])
                    if event["type"] == "assistant_message":
                        assert event["text"] == "Selftest reply.", event
                        break
                assert "tool_result" in seen and "assistant_token" in seen, seen
        finally:
            server.should_exit = True
            thread.join(timeout=10)


def voicetest() -> int:
    """Packaged build on Windows: prove the voice parts are bundled and work.

    Prints one line per part; exit code 1 if Windows voices or the player fail.
    Natural (edge) voices need the internet and are reported, not required.
    """
    import tempfile
    from pathlib import Path

    from .voice.mic import mic_available, to_wav
    from .voice.player import default_player
    from .voice.tts import EdgeSynthesizer, SapiSynthesizer, TtsError

    settings = load_settings()
    voice_cfg = settings.defaults.get("voice", {})
    ok = True
    try:
        import sounddevice  # noqa: F401

        print("sounddevice: bundled")
    except (ImportError, OSError) as exc:
        print(f"sounddevice: MISSING ({exc})")
        ok = False
    print(f"microphone: {mic_available()}")
    print(f"player: {type(default_player()).__name__}")
    assert to_wav(b"\x00\x00" * 160)[:4] == b"RIFF"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for name, synth in (
            ("windows voice", SapiSynthesizer(out / "scripts")),
            ("edge voice", EdgeSynthesizer(voice_cfg.get("edge_voices", {}))),
        ):
            for text in ("Namaste, main Rishu hoon.", "नमस्ते, मैं रिशु हूँ।"):
                try:
                    audio = synth.synth(text, "male", out)
                    print(
                        f"{name}: ok ({audio.kind}, {audio.path.stat().st_size} bytes) for {text!r}"
                    )
                except TtsError as exc:
                    print(f"{name}: FAILED for {text!r}: {exc}")
                    if name == "windows voice" and text.isascii():
                        ok = False
    from .tools.system import SystemControls

    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / "screen.jpg"
        captured = SystemControls().capture_jpeg(shot)
        size = shot.stat().st_size if captured else 0
        print(f"screen capture for vision: {'ok' if captured else 'FAILED'} ({size} bytes)")
    print("voicetest ok" if ok else "voicetest FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rishu", description="Rishu text chat")
    parser.add_argument("--once", metavar="TEXT", help="run one message and exit")
    parser.add_argument("--autonomy", choices=AUTONOMY_MODES, help="override the autonomy mode")
    parser.add_argument("--offline", action="store_true", help="do not contact any LLM provider")
    parser.add_argument("--selftest", action="store_true", help="check that this build is complete")
    parser.add_argument("--voicetest", action="store_true", help="check the voice parts (Windows)")
    parser.add_argument("--serve", action="store_true", help="run the local server for the app")
    parser.add_argument("--port", type=int, default=0, help="server port (0 picks a free one)")
    parser.add_argument(
        "--exit-with-parent",
        action="store_true",
        help="with --serve: stop when stdin closes (the app that started the core is gone)",
    )
    args = parser.parse_args(argv)

    if args.serve:
        from .api.serve import ensure_streams
        from .config import data_dir

        ensure_streams(data_dir() / "core.log")
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if args.selftest:
        return selftest()
    if args.voicetest:
        return voicetest()
    if args.serve:
        from .api import serve

        return serve(args.port, exit_with_parent=args.exit_with_parent)

    settings = load_settings()
    agent = build_agent(
        settings,
        approver=ConsoleApprover(),
        autonomy=args.autonomy,
        on_event=_print_event,
        use_router=not args.offline,
    )
    if agent.llm is None:
        print("No AI model is set up, so only basic commands work (open apps, time, notes).")
        print("Add a free key, e.g. set GROQ_API_KEY, or run Ollama for a local model.\n")

    if args.once:
        print(agent.run_turn(args.once).reply)
        return 0

    print("Rishu is ready. Type your message (exit to quit).")
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.lower() in ("exit", "quit", "bye"):
            return 0
        print(f"Rishu: {agent.run_turn(text).reply}")


if __name__ == "__main__":
    raise SystemExit(main())
