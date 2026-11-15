"""Rule-based understanding of a few basic commands, used when no LLM is reachable.

Covers Hinglish, Hindi and English for: open an app or website, tell the time,
save a note, list notes. Anything else returns ``None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Intent:
    tool: str
    args: dict[str, Any]


_WAKE = re.compile(r"^(?:hey\s+|ok\s+|are\s+|अरे\s+)?(?:rishu|रिशु)[\s,:!]*", re.IGNORECASE)
_POLITE = re.compile(r"\b(please|plz|zara|jara|ज़रा|जरा|प्लीज़|प्लीज)\b", re.IGNORECASE)

_TIME = re.compile(
    r"(what(?:'s| is)? the time|what time|time kya|kya time|kitne baje|samay kya|time batao|"
    r"टाइम क्या|क्या टाइम|कितने बजे|समय क्या|टाइम बताओ|समय बताओ)|^(?:time|samay|टाइम|समय)\??$",
    re.IGNORECASE,
)
_LIST_NOTES = re.compile(
    r"^(?:show|list)(?: me)?(?: my)? notes$|^(?:mere |meri )?notes (?:dikhao|batao|sunao)$|"
    r"^(?:मेरे )?नोट्स (?:दिखाओ|बताओ|सुनाओ)$",
    re.IGNORECASE,
)
_NOTE = re.compile(
    r"^(?:(?:make|take|write)(?: a)? note(?: that| of)?|note (?:likho|likh lo|karo|kar lo|down)|"
    r"नोट (?:लिखो|लिख लो|करो|कर लो)|note)\s*[:\-,]?\s+(?P<text>.+)$",
    re.IGNORECASE,
)
_OPEN_PREFIX = re.compile(r"^(?:open|launch|start|run)\s+(?P<name>.+)$", re.IGNORECASE)
_OPEN_SUFFIX = re.compile(
    r"^(?P<name>.+?)\s+(?:kholo|khol do|khol dena|kholna|open karo|open kar do|open kardo|"
    r"chalu karo|chalao|start karo|खोलो|खोल दो|खोलना|ओपन करो|ओपन कर दो|चालू करो|चलाओ)$",
    re.IGNORECASE,
)
_DOMAIN = re.compile(r"^(?:https?://)?[\w\-]+(?:\.[\w\-]+)+(?:/\S*)?$")


def parse(text: str) -> Intent | None:
    cleaned = _WAKE.sub("", text.strip())
    cleaned = _POLITE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!?।")
    if not cleaned:
        return None

    if _LIST_NOTES.match(cleaned):
        return Intent("list_notes", {})
    note = _NOTE.match(cleaned)
    if note:
        return Intent("add_note", {"text": note.group("text").strip()})
    if _TIME.search(cleaned):
        return Intent("get_time", {})

    match = _OPEN_PREFIX.match(cleaned) or _OPEN_SUFFIX.match(cleaned)
    if match:
        name = match.group("name").strip().strip("\"'")
        name = re.sub(r"\s+(?:ko|को)$", "", name)
        if not name or len(name) > 80:
            return None
        if _DOMAIN.match(name):
            return Intent("open_url", {"url": name})
        return Intent("open_app", {"name": name})
    return None
