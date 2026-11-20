"""High-level control of the current tab in Rishu's browser."""

from __future__ import annotations

import base64
import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from . import scripts
from .cdp import CdpError, CdpSession, Socket, connect_socket
from .chrome import BrowserError, ChromeLauncher

# Buttons whose label suggests a lasting or outward effect always need approval.
RISKY_WORDS = re.compile(
    r"\b(submit|lock|send|delete|remove|pay|payment|purchase|buy|order|checkout|confirm|approve|"
    r"publish|post|save|transfer|withdraw|sign ?out|log ?out|unsubscribe|upload|share|apply|"
    r"finali[sz]e|grade|release|accept|decline|reject|archive|block|report|"
    r"bhej|bhejo|hatao|mitao|jama|bhugtan|bhuktan)\b",
    re.IGNORECASE,
)
# Tabs are not here: sites use them as switches too (Present / Absent).
NAV_ROLES = {"link", "treeitem"}
SEARCH_HINT = re.compile(r"search|khoj|find|filter|dhoondh", re.IGNORECASE)

KEYS: dict[str, tuple[str, str, int]] = {
    "enter": ("Enter", "Enter", 13),
    "tab": ("Tab", "Tab", 9),
    "escape": ("Escape", "Escape", 27),
    "backspace": ("Backspace", "Backspace", 8),
    "arrowdown": ("ArrowDown", "ArrowDown", 40),
    "arrowup": ("ArrowUp", "ArrowUp", 38),
    "arrowleft": ("ArrowLeft", "ArrowLeft", 37),
    "arrowright": ("ArrowRight", "ArrowRight", 39),
    "pagedown": ("PageDown", "PageDown", 34),
    "pageup": ("PageUp", "PageUp", 33),
    "space": (" ", "Space", 32),
}


def site_of(url: str) -> str:
    return urlparse(url).hostname or url


def describe_target(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("ids", {}).get("lexytatestid") or item.get("tag", "element")
    row = item.get("row") or ""
    text = f'{item.get("role", "element")} "{name}"'
    if row and name.lower() not in row.lower()[:20]:
        text += f' (row: "{row[:60]}")'
    return text


def click_risk(item: dict[str, Any] | None) -> int:
    """0 = moves around (links, tabs, pages), 1 = changes something small, 2 = lasting/outward."""
    if item is None:
        return 2  # unknown target: ask
    label = f"{item.get('name', '')} {' '.join(item.get('ids', {}).values())}"
    if RISKY_WORDS.search(label) or item.get("type") == "submit":
        return 2
    if item.get("role") in NAV_ROLES or label.strip().lower() in {
        "next",
        "previous",
        "back",
        "aage",
        "peeche",
    }:
        return 0
    if label.strip().isdigit() and item.get("role") == "button":
        return 0  # a page number
    return 1


class Browser:
    """Rishu's browser window: one current tab, page outline with refs, actions."""

    def __init__(
        self,
        launcher: ChromeLauncher,
        *,
        connect: Callable[[str], Socket] = connect_socket,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.launcher = launcher
        self._connect = connect
        self._sleep = sleep
        self._session: CdpSession | None = None
        self._target: str | None = None
        self._world: tuple[str, int] | None = None  # (frame id, isolated context id)
        self._lock = threading.RLock()
        self.items: dict[str, dict[str, Any]] = {}  # ref -> description, from the last outline
        self.url = ""

    # ---- connection ----------------------------------------------------------

    def session(self, start_url: str = "about:blank") -> CdpSession:
        with self._lock:
            if self._session is not None and not self._session.closed:
                return self._session
            port = self.launcher.ensure(start_url)
            pages = self.launcher.pages(port)
            chosen = next((p for p in pages if p.get("id") == self._target), None)
            if chosen is None:
                normal = [
                    p
                    for p in pages
                    if not str(p.get("url", "")).startswith(("devtools:", "chrome-extension:"))
                ]
                chosen = normal[0] if normal else self.launcher.new_page(port)
            self._target = chosen.get("id")
            self.launcher.activate(port, self._target or "")
            self._session = CdpSession(chosen["webSocketDebuggerUrl"], connect=self._connect)
            self._world = None
            self._session.call("Page.enable")
            self._session.call("Runtime.enable")
            return self._session

    def _context(self) -> int:
        """Rishu's isolated JavaScript world in the current page (new after each navigation)."""
        session = self.session()
        tree = session.call("Page.getFrameTree")
        frame = tree["frameTree"]["frame"]["id"]
        loader = tree["frameTree"]["frame"].get("loaderId", "")
        key = f"{frame}:{loader}"
        if self._world is None or self._world[0] != key:
            world = session.call(
                "Page.createIsolatedWorld", {"frameId": frame, "worldName": "rishu"}
            )
            self._world = (key, int(world["executionContextId"]))
        return self._world[1]

    def run(self, function: str, *args: Any, timeout: float = 20) -> Any:
        session = self.session()
        try:
            context = self._context()
        except CdpError:
            self._world = None
            context = self._context()
        result = session.call(
            "Runtime.evaluate",
            {
                "expression": scripts.call(function, *args),
                "contextId": context,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            text = (details.get("exception") or {}).get("description") or details.get(
                "text", "error"
            )
            raise CdpError(f"page script failed: {str(text)[:200]}")
        return (result.get("result") or {}).get("value")

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.close()
            self._session = None

    # ---- navigation ------------------------------------------------------------

    def wait_ready(self, timeout: float = 20) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.run(scripts.READY, timeout=5) == "complete":
                    break
            except CdpError:
                pass
            self._sleep(0.25)
        self._sleep(0.8)  # single-page apps keep drawing after "complete"

    def open(self, url: str) -> dict[str, Any]:
        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise BrowserError("only http and https pages can be opened")
        with self._lock:
            session = self.session(url)
            current = session.call(
                "Runtime.evaluate", {"expression": "location.href", "returnByValue": True}
            )
            if (current.get("result") or {}).get("value") != url:
                session.call("Page.navigate", {"url": url})
            self._world = None
            self.items = {}
            self.wait_ready()
            return self.outline()

    def outline(self) -> dict[str, Any]:
        with self._lock:
            page = self.run(scripts.OUTLINE) or {}
            self.items = {item["ref"]: item for item in page.get("items", [])}
            self.url = page.get("url", "")
            return page

    def wait_for_text(self, text: str, timeout: float = 10) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.run(scripts.HAS_TEXT, text, timeout=5):
                    return True
            except CdpError:
                pass
            self._sleep(0.3)
        return False

    # ---- actions -----------------------------------------------------------------

    def _settle(self) -> None:
        self._sleep(0.6)
        self._world = None if self._navigated() else self._world

    def _navigated(self) -> bool:
        try:
            return self.run("() => location.href", timeout=5) != self.url
        except CdpError:
            return True

    def click(self, ref: str) -> dict[str, Any]:
        with self._lock:
            point = self.run(scripts.POINT, ref)
            if not point or not point.get("found"):
                raise BrowserError(f"element {ref} is no longer on the page; read the page again")
            if point.get("clear"):
                session = self.session()
                x, y = point["x"], point["y"]
                session.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                for kind in ("mousePressed", "mouseReleased"):
                    session.call(
                        "Input.dispatchMouseEvent",
                        {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1},
                    )
            else:
                self.run(scripts.CLICK_FALLBACK, ref)  # covered by an overlay: click it directly
            self._settle()
            return point.get("info") or {}

    def type(self, ref: str, text: str, press_enter: bool = False) -> dict[str, Any]:
        with self._lock:
            focus = self.run(scripts.FOCUS, ref)
            if not focus or not focus.get("found"):
                raise BrowserError(f"field {ref} is no longer on the page; read the page again")
            if focus.get("type") == "password":
                raise BrowserError(
                    "Rishu never types passwords; please sign in yourself in Rishu's browser window"
                )
            session = self.session()
            if text:
                session.call("Input.insertText", {"text": text})
            else:
                self.press("backspace")
            if press_enter:
                self.press("enter")
            self._settle()
            return focus

    def press(self, key: str) -> None:
        name = key.lower().replace(" ", "")
        if name not in KEYS:
            raise BrowserError(f"unknown key '{key}'")
        key_name, code, vk = KEYS[name]
        session = self.session()
        down: dict[str, Any] = {
            "type": "keyDown",
            "key": key_name,
            "code": code,
            "windowsVirtualKeyCode": vk,
        }
        if name == "enter":
            down["text"] = "\r"
        session.call("Input.dispatchKeyEvent", down)
        session.call(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": key_name, "code": code, "windowsVirtualKeyCode": vk},
        )

    def select(self, ref: str, option: str) -> dict[str, Any]:
        with self._lock:
            result = self.run(scripts.SELECT_OPTION, ref, option) or {}
            if not result.get("ok"):
                options = ", ".join(result.get("options", []))
                raise BrowserError(
                    f"{result.get('reason', 'cannot select')}{': ' + options if options else ''}"
                )
            self._settle()
            return result

    # ---- teach mode: record what the user does ----------------------------------

    def start_recording(self, on_step: Callable[[dict[str, Any]], None]) -> str:
        """Record the user's clicks, typing and page changes until stop_recording()."""
        with self._lock:
            self.stop_recording()
            session = self.session()
            session.call(
                "Runtime.addBinding", {"name": "__rishuRecord", "executionContextName": "rishu"}
            )
            added = session.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": scripts.RECORDER, "worldName": "rishu"},
            )
            self._recording = (session, added.get("identifier", ""))

            def listener(method: str, params: dict[str, Any]) -> None:
                if method == "Runtime.bindingCalled" and params.get("name") == "__rishuRecord":
                    try:
                        step = json.loads(params.get("payload") or "{}")
                    except ValueError:
                        return
                    if isinstance(step, dict):
                        on_step(step)
                elif method == "Page.frameNavigated":
                    frame = params.get("frame") or {}
                    if not frame.get("parentId"):
                        self._world = None
                        on_step(
                            {
                                "kind": "navigated",
                                "url": frame.get("url", ""),
                                "at": time.time() * 1000,
                            }
                        )

            self._unlisten = session.on_event(listener)
            self._world = None
            context = self._context()
            session.call(
                "Runtime.evaluate",
                {"expression": scripts.RECORDER, "contextId": context, "returnByValue": True},
            )
            return self.run("() => location.href", timeout=5) or ""

    def stop_recording(self) -> None:
        recording = getattr(self, "_recording", None)
        if not recording:
            return
        session, identifier = recording
        self._recording = None
        unlisten = getattr(self, "_unlisten", None)
        if unlisten:
            unlisten()
        if session.closed:
            return
        try:
            if identifier:
                session.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": identifier})
            # The recorder left in the open page goes quiet: its binding is gone.
            session.call("Runtime.removeBinding", {"name": "__rishuRecord"})
            self._world = None
        except CdpError:
            pass

    def find(self, target: dict[str, Any], timeout: float = 10) -> dict[str, Any] | None:
        """Wait for the control a taught step meant; None if it never shows up."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                found = self.run(scripts.FIND, target, timeout=10) or {}
            except CdpError:
                found = {}
            if found.get("found"):
                self.items[found["ref"]] = {**(found.get("info") or {}), "ref": found["ref"]}
                return found
            if time.monotonic() >= deadline:
                return None
            self._world = None
            self._sleep(0.5)

    def screenshot(self, quality: int = 70) -> bytes:
        data = self.session().call("Page.captureScreenshot", {"format": "jpeg", "quality": quality})
        return base64.b64decode(data["data"])


def format_outline(
    page: dict[str, Any], limit: int = 150, text_chars: int = 1500, find: str = ""
) -> str:
    """The page as text for the model: headings, then the controls with their refs.

    ``find`` keeps only controls whose name or row contains it (long pages).
    """
    lines = [f"Page: {page.get('title', '')} — {page.get('url', '')}"]
    if page.get("headings"):
        lines.append("Headings: " + " | ".join(page["headings"]))
    items = page.get("items", [])
    if find:
        needle = find.lower()
        items = [i for i in items if needle in f"{i.get('name', '')} {i.get('row', '')}".lower()]
        lines.append(f'Controls matching "{find}" (use the [ref] to click or type):')
    else:
        lines.append("Controls (use the [ref] to click or type):")
    for item in items[:limit]:
        parts = [f'[{item["ref"]}] {item.get("role", item.get("tag"))} "{item.get("name", "")}"']
        for key in ("selected", "checked", "pressed", "expanded"):
            if key in item:
                parts.append(f"{key}={item[key]}")
        if item.get("value"):
            parts.append(f'value="{item["value"]}"')
        if item.get("disabled"):
            parts.append("disabled")
        if (
            item.get("row")
            and item.get("name", "").lower()
            not in item["row"].lower()[: len(item.get("name", "")) + 1]
        ):
            parts.append(f'row="{item["row"][:90]}"')
        lines.append("  " + " ".join(parts))
    more = len(items) - limit
    if more > 0:
        lines.append(f"  … and {more} more controls (read again with find=… to narrow)")
    if page.get("text") and text_chars > 0:
        lines.append("Visible text: " + page["text"][:text_chars])
    return "\n".join(lines)
