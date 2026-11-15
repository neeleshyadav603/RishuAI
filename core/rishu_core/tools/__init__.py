"""Built-in tools and the default registry."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings, data_dir
from ..permissions import Risk
from . import apps, notes, web
from .registry import Tool, ToolRegistry, ToolResult

__all__ = ["Tool", "ToolRegistry", "ToolResult", "build_registry"]


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def get_time(now: Callable[[], datetime] = datetime.now) -> ToolResult:
    current = now().astimezone()
    text = current.strftime("%A, %d %B %Y, %I:%M %p (%Z)")
    return ToolResult(True, text, data={"iso": current.isoformat()})


def build_registry(
    settings: Settings,
    *,
    launcher: apps.AppLauncher | None = None,
    url_opener: Callable[[str], bool] | None = None,
    search_backend: web.SearchBackend | None = None,
    http_transport: httpx.BaseTransport | None = None,
    resolver: web.Resolver | None = None,
    home: Path | None = None,
    now: Callable[[], datetime] = datetime.now,
) -> ToolRegistry:
    """Create the registry with every Phase 1 tool. Dependencies are injectable for tests."""
    registry = ToolRegistry()
    web_cfg = settings.defaults.get("web", {})
    launcher = launcher or apps.AppLauncher(settings.app_aliases)
    store = notes.NotesStore((home or data_dir()) / "notes.jsonl")

    registry.register(
        Tool(
            name="get_time",
            description="Get the current local date and time on the user's device.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=lambda: get_time(now),
        )
    )
    registry.register(
        Tool(
            name="open_app",
            description=(
                "Open an installed application on the user's computer by its name, "
                "for example 'chrome', 'notepad', 'calculator', 'whatsapp'."
            ),
            parameters=_obj(
                {"name": {"type": "string", "description": "App name as the user said it"}},
                ["name"],
            ),
            risk=Risk.R1,
            handler=lambda name: launcher.launch(name),
            preview_fn=lambda a: f"Open the app '{a.get('name', '')}'",
        )
    )
    registry.register(
        Tool(
            name="open_url",
            description="Open a web address (http/https) in the user's default browser.",
            parameters=_obj(
                {"url": {"type": "string", "description": "Full web address"}}, ["url"]
            ),
            risk=Risk.R1,
            handler=lambda url: (
                apps.open_url(url, url_opener) if url_opener else apps.open_url(url)
            ),
            preview_fn=lambda a: f"Open {a.get('url', '')} in the browser",
        )
    )
    registry.register(
        Tool(
            name="web_search",
            description=(
                "Search the web for current information. Returns numbered results with "
                "title, URL and snippet. Use read_page to read a result in full."
            ),
            parameters=_obj(
                {"query": {"type": "string", "description": "Short search query"}}, ["query"]
            ),
            risk=Risk.R0,
            handler=lambda query: web.web_search(
                query, search_backend, int(web_cfg.get("search_results", 5))
            ),
            untrusted_output=True,
        )
    )
    registry.register(
        Tool(
            name="read_page",
            description="Fetch a public web page and return its main text. Use for details behind a search result.",
            parameters=_obj(
                {"url": {"type": "string", "description": "The page's web address"}}, ["url"]
            ),
            risk=Risk.R0,
            handler=lambda url: web.read_page(
                url,
                transport=http_transport,
                resolver=resolver,
                max_chars=int(web_cfg.get("page_max_chars", 6000)),
                max_bytes=int(web_cfg.get("page_max_bytes", 2_000_000)),
                timeout=float(web_cfg.get("timeout_seconds", 15)),
            ),
            untrusted_output=True,
        )
    )
    registry.register(
        Tool(
            name="add_note",
            description="Save a short note for the user.",
            parameters=_obj({"text": {"type": "string", "description": "The note text"}}, ["text"]),
            risk=Risk.R1,
            handler=lambda text: notes.add_note(store, text),
            preview_fn=lambda a: f"Save the note: {a.get('text', '')}",
        )
    )
    registry.register(
        Tool(
            name="list_notes",
            description="List the user's most recent notes.",
            parameters=_obj(
                {"limit": {"type": "integer", "description": "How many notes (default 10)"}}
            ),
            risk=Risk.R0,
            handler=lambda limit=10: notes.list_notes(store, limit),
        )
    )
    return registry
