"""Browser tools: Rishu works inside web pages in its own Chrome window.

Page content is untrusted data. Clicking links is R0 (moving around), small
changes (tabs, typing, choosing) are R1, and anything whose label suggests a
lasting or outward effect (submit, send, delete, lock, pay, save…) is R2.
After a page was read, the untrusted-content rule raises each by one level.
"""

from __future__ import annotations

from typing import Any

from ..browser import (
    Browser,
    BrowserError,
    CdpError,
    click_risk,
    describe_target,
    format_outline,
    site_of,
)
from ..permissions import Risk
from .registry import ToolResult


def _page_result(
    browser: Browser, page: dict[str, Any], prefix: str = "", **fmt: Any
) -> ToolResult:
    text = format_outline(page, **fmt)
    return ToolResult(
        True,
        (prefix + "\n" if prefix else "") + text,
        untrusted=True,
        source=page.get("url", ""),
        data={"url": page.get("url", ""), "title": page.get("title", "")},
    )


def _fail(exc: Exception) -> ToolResult:
    message = str(exc)
    if isinstance(exc, CdpError) and "closed" in message:
        message = "Rishu's browser window was closed. Open the page again."
    return ToolResult(False, message)


class BrowserTools:
    def __init__(self, browser: Browser):
        self.browser = browser

    # ---- handlers -----------------------------------------------------------

    def open(self, url: str) -> ToolResult:
        if "://" not in url:
            url = "https://" + url.strip()
        try:
            page = self.browser.open(url)
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        note = (
            "Opened in Rishu's browser window. If the site asks to sign in, tell the user to sign in "
            "there themselves (Rishu never types passwords); it stays signed in next time."
        )
        return _page_result(self.browser, page, note)

    def read(self, find: str = "") -> ToolResult:
        try:
            page = self.browser.outline()
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        return _page_result(self.browser, page, find=find, limit=200 if find else 150)

    def click(self, ref: str) -> ToolResult:
        target = self.browser.items.get(ref)
        try:
            info = self.browser.click(ref)
            page = self.browser.outline()
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        done = f"Clicked {describe_target(info or target or {'name': ref})}."
        return _page_result(self.browser, page, done, limit=80, text_chars=600)

    def type(self, ref: str, text: str, press_enter: bool = False) -> ToolResult:
        target = self.browser.items.get(ref)
        try:
            self.browser.type(ref, text, press_enter)
            page = self.browser.outline()
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        done = f'Typed "{text}" into {describe_target(target or {"name": ref})}' + (
            " and pressed Enter." if press_enter else "."
        )
        return _page_result(self.browser, page, done, limit=80, text_chars=600)

    def select(self, ref: str, option: str) -> ToolResult:
        try:
            chosen = self.browser.select(ref, option)
            page = self.browser.outline()
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        return _page_result(
            self.browser, page, f'Chose "{chosen.get("chosen", option)}".', limit=80, text_chars=600
        )

    def press(self, key: str) -> ToolResult:
        try:
            self.browser.press(key)
            page = self.browser.outline()
        except (BrowserError, CdpError) as exc:
            return _fail(exc)
        return _page_result(self.browser, page, f"Pressed {key}.", limit=80, text_chars=600)

    # ---- risk and previews ------------------------------------------------------

    def click_risk(self, args: dict[str, Any]) -> Risk:
        return Risk(click_risk(self.browser.items.get(str(args.get("ref", "")))))

    def type_risk(self, args: dict[str, Any]) -> Risk:
        target = self.browser.items.get(str(args.get("ref", ""))) or {}
        if args.get("press_enter"):
            label = f"{target.get('name', '')} {target.get('role', '')} {' '.join(target.get('ids', {}).values())}"
            from ..browser.page import SEARCH_HINT

            return Risk.R1 if SEARCH_HINT.search(label) else Risk.R2
        return Risk.R1

    def _site(self) -> str:
        return site_of(self.browser.url) if self.browser.url else "the page"

    def click_preview(self, args: dict[str, Any]) -> str:
        target = self.browser.items.get(str(args.get("ref", "")))
        what = describe_target(target) if target else f"element {args.get('ref')}"
        return f"Click {what} on {self._site()}"

    def type_preview(self, args: dict[str, Any]) -> str:
        target = self.browser.items.get(str(args.get("ref", "")))
        what = describe_target(target) if target else f"field {args.get('ref')}"
        enter = " and press Enter" if args.get("press_enter") else ""
        return f'Type "{args.get("text", "")}" into {what} on {self._site()}{enter}'

    def select_preview(self, args: dict[str, Any]) -> str:
        target = self.browser.items.get(str(args.get("ref", "")))
        what = describe_target(target) if target else f"drop-down {args.get('ref')}"
        return f'Choose "{args.get("option", "")}" in {what} on {self._site()}'


def register(registry: Any, browser: Browser, vision_ask: Any = None) -> BrowserTools:
    from . import Tool, _obj

    tools = BrowserTools(browser)
    ref = {
        "type": "string",
        "description": "The [ref] of the control from the latest page outline, e.g. e12",
    }
    registry.register(
        Tool(
            name="browser_open",
            description=(
                "Open a web page in Rishu's own browser window (Chrome/Edge) to work inside it: "
                "college LMS, Google Sheets, Gmail, any site. Returns the page outline with [ref]s. "
                "The user signs in once in that window; never ask for or type passwords."
            ),
            parameters=_obj(
                {
                    "url": {
                        "type": "string",
                        "description": "Full address, e.g. https://lms.lexyta.com",
                    }
                },
                ["url"],
            ),
            risk=Risk.R1,
            handler=tools.open,
            untrusted_output=True,
            preview_fn=lambda a: f"Open {a.get('url', '')} in Rishu's browser",
        )
    )
    registry.register(
        Tool(
            name="browser_read",
            description=(
                "Read the current page in Rishu's browser: title, headings, controls with [ref]s "
                "(buttons, links, fields, tabs, with the row text they belong to) and visible text. "
                "Use find to list only controls whose name or row contains a word (a student's name, a roll number)."
            ),
            parameters=_obj(
                {"find": {"type": "string", "description": "Optional word to narrow the list"}}
            ),
            risk=Risk.R0,
            handler=tools.read,
            untrusted_output=True,
        )
    )
    registry.register(
        Tool(
            name="browser_click",
            description="Click a control in Rishu's browser by its [ref] (link, button, tab, checkbox).",
            parameters=_obj({"ref": ref}, ["ref"]),
            risk=Risk.R1,
            handler=tools.click,
            untrusted_output=True,
            risk_fn=tools.click_risk,
            preview_fn=tools.click_preview,
        )
    )
    registry.register(
        Tool(
            name="browser_type",
            description=(
                "Type text into a field in Rishu's browser by its [ref]; it replaces what is there. "
                "press_enter submits (search boxes, chat boxes)."
            ),
            parameters=_obj(
                {"ref": ref, "text": {"type": "string"}, "press_enter": {"type": "boolean"}},
                ["ref", "text"],
            ),
            risk=Risk.R1,
            handler=tools.type,
            untrusted_output=True,
            risk_fn=tools.type_risk,
            preview_fn=tools.type_preview,
        )
    )
    registry.register(
        Tool(
            name="browser_select",
            description="Choose an option in a drop-down in Rishu's browser by its [ref] and the option text.",
            parameters=_obj({"ref": ref, "option": {"type": "string"}}, ["ref", "option"]),
            risk=Risk.R1,
            handler=tools.select,
            untrusted_output=True,
            preview_fn=tools.select_preview,
        )
    )
    registry.register(
        Tool(
            name="browser_press",
            description="Press a key in Rishu's browser: Enter, Tab, Escape, ArrowDown, ArrowUp, PageDown, PageUp, Space.",
            parameters=_obj({"key": {"type": "string"}}, ["key"]),
            risk=Risk.R1,
            handler=tools.press,
            untrusted_output=True,
            risk_fn=lambda a: Risk.R2 if str(a.get("key", "")).lower() == "enter" else Risk.R1,
            preview_fn=lambda a: f"Press {a.get('key', '')} in Rishu's browser",
        )
    )
    if vision_ask is not None:

        def look(question: str = "What is on this page?") -> ToolResult:
            try:
                picture = browser.screenshot()
            except (BrowserError, CdpError) as exc:
                return _fail(exc)
            try:
                answer = vision_ask(question, picture)
            except Exception as exc:  # noqa: BLE001 - report the model problem
                return ToolResult(False, f"Could not look at the page: {exc}")
            return ToolResult(True, answer, untrusted=True, source=browser.url)

        registry.register(
            Tool(
                name="browser_look",
                description="Look at a screenshot of Rishu's browser page (charts, images, layout the outline misses).",
                parameters=_obj({"question": {"type": "string"}}),
                risk=Risk.R0,
                handler=look,
                untrusted_output=True,
            )
        )
    return tools
