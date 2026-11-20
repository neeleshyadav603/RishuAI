"""Built-in tools and the default registry."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..browser import Browser, ChromeLauncher
from ..config import Settings, data_dir
from ..permissions import Risk
from ..teach import SkillStore
from . import apps, browser, comms, memory, notes, reminders, system, teach, vision, weather, web
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
    uri_opener: Callable[[str], bool] | None = None,
    whatsapp_installed: Callable[[], bool] | None = None,
    controls: system.SystemControls | None = None,
    vision_ask: vision.VisionAsk | None = None,
    web_browser: Browser | None = None,
) -> ToolRegistry:
    """Create the registry with every Phase 1 tool. Dependencies are injectable for tests."""
    registry = ToolRegistry()
    web_cfg = settings.defaults.get("web", {})
    launcher = launcher or apps.AppLauncher(settings.app_aliases)
    store = notes.NotesStore((home or data_dir()) / "notes.jsonl")
    browse = url_opener or (lambda url: bool(apps.webbrowser.open(url)))
    open_uri = uri_opener or comms.default_uri_opener
    wa_installed = whatsapp_installed or comms.whatsapp_app_installed
    controls = controls or system.SystemControls()
    folder = home or data_dir()
    registry.reminders = reminders.ReminderStore(folder / "reminders.json")
    registry.memory = memory.MemoryStore(folder / "memory.json")
    reminder_store, memory_store = registry.reminders, registry.memory

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
    registry.register(
        Tool(
            name="play_youtube",
            description="Open YouTube search results for a song, video or topic in the browser.",
            parameters=_obj(
                {"query": {"type": "string", "description": "What to search on YouTube"}}, ["query"]
            ),
            risk=Risk.R1,
            handler=lambda query: comms.youtube(query, browse),
            preview_fn=lambda a: f"Open YouTube results for '{a.get('query', '')}'",
        )
    )
    registry.register(
        Tool(
            name="browser_search",
            description=(
                "Open Google search results in the user's browser so they can see them. "
                "Use web_search instead when you need to read and answer yourself."
            ),
            parameters=_obj(
                {"query": {"type": "string", "description": "Search words"}}, ["query"]
            ),
            risk=Risk.R1,
            handler=lambda query: comms.browser_search(query, browse),
            preview_fn=lambda a: f"Search Google for '{a.get('query', '')}' in the browser",
        )
    )
    registry.register(
        Tool(
            name="whatsapp_draft",
            description=(
                "Open WhatsApp with a message typed in, ready to send. Without a phone "
                "number the user picks the contact. The user presses Send; this tool never sends."
            ),
            parameters=_obj(
                {
                    "text": {"type": "string", "description": "The message"},
                    "phone": {
                        "type": "string",
                        "description": "Phone number with country code, only if the user gave one; else empty",
                    },
                },
                ["text"],
            ),
            risk=Risk.R2,
            handler=lambda text, phone="": comms.whatsapp_draft(
                text, phone, open_uri, wa_installed
            ),
            preview_fn=lambda a: (
                f"Open WhatsApp{' for ' + a['phone'] if a.get('phone') else ''} with the message: {a.get('text', '')}"
            ),
        )
    )
    registry.register(
        Tool(
            name="email_draft",
            description="Open an email draft in the user's mail app (the user reviews and sends it).",
            parameters=_obj(
                {
                    "to": {"type": "string", "description": "Recipient email address, or empty"},
                    "subject": {"type": "string", "description": "Subject line"},
                    "body": {"type": "string", "description": "Email text"},
                },
                ["subject", "body"],
            ),
            risk=Risk.R2,
            handler=lambda subject, body, to="": comms.email_draft(to, subject, body, open_uri),
            preview_fn=lambda a: (
                f"Open an email draft to {a.get('to') or '(choose)'}: {a.get('subject', '')}"
            ),
        )
    )
    registry.register(
        Tool(
            name="volume",
            description="Change the computer's sound volume: up, down or mute (mute toggles).",
            parameters=_obj(
                {
                    "action": {"type": "string", "enum": ["up", "down", "mute"]},
                    "steps": {
                        "type": "integer",
                        "description": "How much, 1-25 steps of 2% (default 5)",
                    },
                },
                ["action"],
            ),
            risk=Risk.R1,
            handler=lambda action, steps=5: controls.volume(action, steps),
            preview_fn=lambda a: f"Volume {a.get('action', '')}",
        )
    )
    registry.register(
        Tool(
            name="screenshot",
            description="Take a screenshot of the screen and save it in Pictures\\Rishu.",
            parameters=_obj({}),
            risk=Risk.R1,
            handler=controls.screenshot,
            preview_fn=lambda a: "Take a screenshot",
        )
    )
    registry.register(
        Tool(
            name="lock_computer",
            description="Lock the computer (Windows lock screen).",
            parameters=_obj({}),
            risk=Risk.R2,
            handler=controls.lock_pc,
            preview_fn=lambda a: "Lock this computer now",
        )
    )
    registry.register(
        Tool(
            name="battery_status",
            description="Battery level and whether it is charging.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=controls.battery,
        )
    )
    registry.register(
        Tool(
            name="set_reminder",
            description=(
                "Set a reminder or timer. Rishu says it aloud when due. Give either "
                "'minutes' from now or a clock time 'at' like '17:30' or '5:30 pm'."
            ),
            parameters=_obj(
                {
                    "text": {"type": "string", "description": "What to remind about"},
                    "minutes": {"type": "number", "description": "Minutes from now"},
                    "at": {"type": "string", "description": "Clock time, e.g. 17:30"},
                },
                ["text"],
            ),
            risk=Risk.R1,
            handler=lambda text, minutes=None, at=None: reminders.set_reminder(
                reminder_store, text, minutes, at, now
            ),
            preview_fn=lambda a: f"Set a reminder: {a.get('text', '')}",
        )
    )
    registry.register(
        Tool(
            name="list_reminders",
            description="List the reminders that are still waiting.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=lambda: reminders.list_reminders(reminder_store),
        )
    )
    registry.register(
        Tool(
            name="cancel_reminder",
            description="Cancel a reminder by its id (from list_reminders).",
            parameters=_obj({"id": {"type": "string"}}, ["id"]),
            risk=Risk.R1,
            handler=lambda id: reminders.cancel_reminder(reminder_store, id),  # noqa: A006
            preview_fn=lambda a: f"Cancel reminder {a.get('id', '')}",
        )
    )
    registry.register(
        Tool(
            name="remember",
            description=(
                "Save a fact the user explicitly asks you to remember (preferences, people, "
                "routines). Only when the user asks."
            ),
            parameters=_obj(
                {"fact": {"type": "string", "description": "The fact, in one sentence"}}, ["fact"]
            ),
            risk=Risk.R1,
            handler=lambda fact: memory.remember(memory_store, fact),
            preview_fn=lambda a: f"Remember: {a.get('fact', '')}",
        )
    )
    registry.register(
        Tool(
            name="forget",
            description="Forget saved facts that contain these words (when the user asks).",
            parameters=_obj({"about": {"type": "string"}}, ["about"]),
            risk=Risk.R1,
            handler=lambda about: memory.forget(memory_store, about),
            preview_fn=lambda a: f"Forget what I saved about: {a.get('about', '')}",
        )
    )
    registry.register(
        Tool(
            name="list_memories",
            description="List everything the user asked you to remember.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=lambda: memory.list_memories(memory_store),
        )
    )
    registry.register(
        Tool(
            name="weather",
            description="Current weather and today/tomorrow forecast for a city.",
            parameters=_obj(
                {"place": {"type": "string", "description": "City name, e.g. Gurugram"}}, ["place"]
            ),
            risk=Risk.R0,
            handler=lambda place: weather.weather(place, http_transport),
        )
    )
    registry.register(
        Tool(
            name="look_at_screen",
            description=(
                "Take a picture of the user's screen and answer a question about it "
                "(explain what is shown, read an error, describe a diagram)."
            ),
            parameters=_obj(
                {
                    "question": {
                        "type": "string",
                        "description": "What the user wants to know about the screen",
                    }
                },
                ["question"],
            ),
            risk=Risk.R1,
            handler=lambda question: vision.look_at_screen(
                question, controls.capture_jpeg, vision_ask
            ),
            untrusted_output=True,
            preview_fn=lambda a: "Look at the screen",
        )
    )
    registry.browser = web_browser or Browser(ChromeLauncher(folder))
    browser.register(registry, registry.browser, vision_ask)
    registry.teach = teach.register(registry, registry.browser, SkillStore(folder / "skills.json"))
    return registry
