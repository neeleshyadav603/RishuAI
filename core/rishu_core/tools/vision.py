"""Look at the screen: a screenshot goes to a vision model, which describes it."""

from __future__ import annotations

import base64
import tempfile
from collections.abc import Callable
from pathlib import Path

from .registry import ToolResult

# (question, jpeg bytes) -> description, or raises an exception with a reason.
VisionAsk = Callable[[str, bytes], str]

MAX_IMAGE_BYTES = 3_000_000


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def look_at_screen(
    question: str, capture: Callable[[Path], bool], ask: VisionAsk | None
) -> ToolResult:
    if ask is None:
        return ToolResult(False, "Looking at the screen needs an AI model that can see images.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "screen.jpg"
        if not capture(path):
            return ToolResult(False, "I could not take a picture of the screen (Windows only).")
        jpeg = path.read_bytes()
    if len(jpeg) > MAX_IMAGE_BYTES:
        return ToolResult(False, "The screen picture is too large to send.")
    try:
        answer = ask(question.strip() or "Describe what is on the screen.", jpeg)
    except Exception as exc:  # noqa: BLE001 - any model error becomes a plain message
        return ToolResult(False, f"The vision model could not look at the screen ({exc}).")
    if not answer.strip():
        return ToolResult(False, "The vision model gave no answer.")
    # What is on the screen is outside content: data, never instructions.
    return ToolResult(True, answer.strip(), untrusted=True, source="screen")
