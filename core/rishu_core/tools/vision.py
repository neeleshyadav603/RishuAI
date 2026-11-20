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


IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def read_image(
    path: str,
    question: str,
    shrink: Callable[[Path, Path], bool],
    ask: VisionAsk | None,
    work_dir: Path,
) -> ToolResult:
    """Ask the vision model about a photo on this computer (a register page, a notice)."""
    if ask is None:
        return ToolResult(
            False, "Reading photos needs an AI model that can see images (a Groq key)."
        )
    source = Path(path).expanduser()
    if not source.is_file():
        return ToolResult(False, f"Photo not found: {path}. Use find_files to look for it.")
    if source.suffix.lower() not in IMAGE_TYPES:
        return ToolResult(False, "That is not a photo (JPG or PNG).")
    work_dir.mkdir(parents=True, exist_ok=True)
    small = work_dir / "photo.jpg"
    if shrink(source, small):
        picture = small.read_bytes()
    elif source.suffix.lower() in (".jpg", ".jpeg") and source.stat().st_size <= 3_500_000:
        picture = source.read_bytes()
    else:
        return ToolResult(False, "The photo is too large to send; please share a smaller JPG.")
    try:
        answer = ask(question, picture)
    except Exception as exc:  # noqa: BLE001 - report the model problem
        return ToolResult(False, f"Could not read the photo: {exc}")
    finally:
        small.unlink(missing_ok=True)
    return ToolResult(True, answer, untrusted=True, source=str(source))
