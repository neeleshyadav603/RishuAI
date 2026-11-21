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
from . import (
    apps,
    browser,
    comms,
    contacts,
    lexyta,
    memory,
    notes,
    reminders,
    sheets,
    system,
    teach,
    teacher,
    vision,
    weather,
    web,
)
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
    whatsapp_press_send: Callable[[], bool] | None = None,
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
    people = contacts.ContactStore(folder / "contacts.json")
    registry.contacts = people
    press_send = whatsapp_press_send or comms.press_send_in_whatsapp

    def send_whatsapp(to: str, text: str) -> ToolResult:
        contact, problem = contacts.resolve(people, to)
        if contact is None:
            return ToolResult(False, problem)
        return comms.whatsapp_send(contact, text, open_uri, wa_installed, press_send)

    registry.register(
        Tool(
            name="whatsapp_send",
            description=(
                "Send a WhatsApp message to a contact saved in Rishu (by name) or to a number, through the "
                "official WhatsApp Desktop app. The user approves the exact recipient and text first. "
                "Write the message the way the user would, in their language. One person at a time."
            ),
            parameters=_obj(
                {
                    "to": {
                        "type": "string",
                        "description": "Contact name as saved in Rishu, or a phone number",
                    },
                    "text": {"type": "string", "description": "The message"},
                },
                ["to", "text"],
            ),
            risk=Risk.R2,
            handler=send_whatsapp,
            preview_fn=lambda a: contacts.describe(people, a),
        )
    )
    registry.register(
        Tool(
            name="save_contact",
            description="Save or update a contact in Rishu's encrypted address book: name, WhatsApp number, e-mail.",
            parameters=_obj(
                {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                },
                ["name"],
            ),
            risk=Risk.R1,
            handler=lambda name, phone="", email="": contacts.save_contact(
                people, name, phone, email
            ),
            preview_fn=lambda a: (
                f"Save contact {a.get('name', '')} {a.get('phone', '')} {a.get('email', '')}".strip()
            ),
        )
    )
    registry.register(
        Tool(
            name="list_contacts",
            description="List the contacts saved in Rishu.",
            parameters=_obj({}),
            risk=Risk.R0,
            handler=lambda: contacts.list_contacts(people),
        )
    )
    registry.register(
        Tool(
            name="forget_contact",
            description="Delete a contact from Rishu's address book.",
            parameters=_obj({"name": {"type": "string"}}, ["name"]),
            risk=Risk.R1,
            handler=lambda name: (
                ToolResult(True, f"Deleted {name}.")
                if people.delete(name)
                else ToolResult(False, f"No contact called {name}.")
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
    lexyta.register(registry, registry.browser)
    _register_files(registry, folder, controls, vision_ask)
    _register_teacher(registry, folder, now, open_uri)
    return registry


def _register_files(
    registry: ToolRegistry, folder: Path, controls: system.SystemControls, vision_ask: Any
) -> None:
    """Files on this computer: find them, read and fill sheets, read photos."""
    registry.register(
        Tool(
            name="find_files",
            description=(
                "Find files on this computer by part of the name (Desktop, Documents, Downloads, OneDrive), "
                "newest first. Use before reading or filling a sheet or photo the user names."
            ),
            parameters=_obj(
                {"query": {"type": "string", "description": "Words from the file name"}}, ["query"]
            ),
            risk=Risk.R0,
            handler=sheets.find_files,
        )
    )
    registry.register(
        Tool(
            name="sheet_read",
            description="Read an Excel (.xlsx) or CSV file: columns and the first rows.",
            parameters=_obj({"path": {"type": "string"}, "sheet": {"type": "string"}}, ["path"]),
            risk=Risk.R0,
            handler=sheets.read_sheet,
            untrusted_output=True,
        )
    )
    registry.register(
        Tool(
            name="sheet_fill",
            description=(
                "Fill one column of an Excel (.xlsx) or CSV file by person: values maps a name or roll number "
                '(or its last digits) to the value, e.g. {"Aryan": "8", "12": "9"}. A missing column is '
                "added. Nothing is written if anyone does not match exactly one row."
            ),
            parameters=_obj(
                {
                    "path": {"type": "string"},
                    "column": {
                        "type": "string",
                        "description": "Column title to fill, e.g. 'Assignment 1' or '21 Nov'",
                    },
                    "values": {"type": "object", "description": "Name or roll number -> value"},
                    "sheet": {"type": "string"},
                    "match_column": {
                        "type": "string",
                        "description": "Optional: the column with names or roll numbers",
                    },
                },
                ["path", "column", "values"],
            ),
            risk=Risk.R2,
            handler=lambda path, column, values, sheet="", match_column="": sheets.fill_sheet(
                path, column, values, sheet, match_column, backup_dir=folder / "backups"
            ),
            preview_fn=sheets.preview_fill,
        )
    )
    registry.register(
        Tool(
            name="read_image",
            description=(
                "Read a photo on this computer with the vision model, e.g. a handwritten attendance register: "
                "ask for every row as 'name | roll number | value' so it can go into a sheet."
            ),
            parameters=_obj(
                {"path": {"type": "string"}, "question": {"type": "string"}}, ["path", "question"]
            ),
            risk=Risk.R0,
            handler=lambda path, question: vision.read_image(
                path, question, controls.shrink_image, vision_ask, folder / "tmp"
            ),
            untrusted_output=True,
        )
    )


OPENABLE = (
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".csv",
    ".pptx",
    ".ppt",
    ".pdf",
    ".txt",
    ".md",
    ".odt",
    ".ods",
    ".odp",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp3",
    ".mp4",
    ".mkv",
    ".wav",
)


def _register_teacher(
    registry: ToolRegistry,
    folder: Path,
    now: Callable[[], datetime],
    open_uri: Callable[[str], bool],
) -> None:
    """Timetable, lecture reminders and class material files."""
    table = teacher.Timetable(folder / "timetable.json", now=now)
    registry.timetable = table
    entry = {
        "type": "object",
        "properties": {
            "day": {"type": "string", "description": "monday … sunday (or somvar … ravivar)"},
            "start": {"type": "string", "description": "e.g. 9:30 or 2 pm"},
            "end": {"type": "string"},
            "subject": {"type": "string"},
            "group": {"type": "string", "description": "Class/section, e.g. B.Tech CSE 5 A"},
            "room": {"type": "string"},
        },
        "required": ["day", "start", "subject"],
    }

    def add(entries: list, replace: bool = False) -> ToolResult:
        added, problems = table.add([e for e in entries if isinstance(e, dict)], replace)
        text = (
            f"Saved {len(added)} classes"
            + (" (the old timetable was replaced)" if replace else "")
            + "."
        )
        if problems:
            text += " " + "; ".join(problems)
        return ToolResult(bool(added), text)

    registry.register(
        Tool(
            name="timetable_add",
            description=(
                "Save the user's weekly class timetable (one entry per lecture). Rishu then answers "
                "'aaj kaunsi class hai' and reminds the user before each lecture. replace=true replaces the whole timetable."
            ),
            parameters=_obj(
                {"entries": {"type": "array", "items": entry}, "replace": {"type": "boolean"}},
                ["entries"],
            ),
            risk=Risk.R1,
            handler=add,
            preview_fn=lambda a: f"Save {len(a.get('entries') or [])} classes in the timetable",
        )
    )
    registry.register(
        Tool(
            name="timetable_show",
            description="The user's classes for a day: 'today' (default), 'tomorrow', a weekday, or 'week'.",
            parameters=_obj({"day": {"type": "string"}}),
            risk=Risk.R0,
            handler=lambda day="": teacher.show(table, day, now),
        )
    )
    registry.register(
        Tool(
            name="timetable_remove",
            description="Remove classes from the timetable: all of a day, or the one starting at a time.",
            parameters=_obj({"day": {"type": "string"}, "start": {"type": "string"}}, ["day"]),
            risk=Risk.R1,
            handler=lambda day, start="": ToolResult(
                True, f"Removed {table.remove(day, start)} classes."
            ),
        )
    )
    registry.register(
        Tool(
            name="make_document",
            description=(
                "Create a Word (.docx) file in Documents/Rishu: class notes, a question paper, a quiz with an "
                "answer key, a letter. content is simple markdown (# headings, - bullets, 1. numbers, **bold**, | tables |)."
            ),
            parameters=_obj(
                {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "file_name": {"type": "string"},
                },
                ["title", "content"],
            ),
            risk=Risk.R1,
            handler=lambda title, content, file_name="": teacher.make_document(
                title, content, file_name
            ),
            preview_fn=lambda a: (
                f"Create the Word file '{a.get('file_name') or a.get('title', '')}' in Documents/Rishu"
            ),
        )
    )
    registry.register(
        Tool(
            name="make_spreadsheet",
            description="Create an Excel (.xlsx) file in Documents/Rishu, e.g. a result sheet or attendance summary.",
            parameters=_obj(
                {
                    "title": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "rows": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "file_name": {"type": "string"},
                },
                ["title", "columns", "rows"],
            ),
            risk=Risk.R1,
            handler=lambda title, columns, rows, file_name="": teacher.make_spreadsheet(
                title, columns, rows, file_name
            ),
            preview_fn=lambda a: (
                f"Create the Excel file '{a.get('file_name') or a.get('title', '')}' in Documents/Rishu"
            ),
        )
    )

    def open_file(path: str) -> ToolResult:
        target = Path(path).expanduser()
        if not target.is_file():
            return ToolResult(False, f"File not found: {path}. Use find_files.")
        if target.suffix.lower() not in OPENABLE:
            return ToolResult(
                False,
                "Rishu opens documents, sheets, slides, PDFs, pictures and media only, not programs.",
            )
        if not open_uri(str(target)):
            return ToolResult(False, "Could not open the file.")
        return ToolResult(True, f"Opened {target.name}.")

    registry.register(
        Tool(
            name="open_file",
            description="Open a document, sheet, presentation, PDF, picture or media file on this computer (not programs).",
            parameters=_obj({"path": {"type": "string"}}, ["path"]),
            risk=Risk.R1,
            handler=open_file,
            preview_fn=lambda a: f"Open {a.get('path', '')}",
        )
    )
