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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rishu", description="Rishu text chat")
    parser.add_argument("--once", metavar="TEXT", help="run one message and exit")
    parser.add_argument("--autonomy", choices=AUTONOMY_MODES, help="override the autonomy mode")
    parser.add_argument("--offline", action="store_true", help="do not contact any LLM provider")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

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
