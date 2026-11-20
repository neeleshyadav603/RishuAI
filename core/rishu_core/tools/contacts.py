"""Rishu's own small address book (names → WhatsApp numbers, e-mails), encrypted.

WhatsApp Desktop opens a chat only by number (the official click-to-chat
link), so the user tells Rishu a contact's number once ("Shruti ka number
98…"). Matching a spoken name is careful: two possible people is a question,
never a guess.
"""

from __future__ import annotations

import difflib
import json
import threading
from pathlib import Path
from typing import Any

from ..security.vault import Vault, default_vault
from .comms import clean_phone
from .registry import ToolResult


def _norm(text: str) -> str:
    return " ".join(text.lower().replace(".", " ").split())


class ContactStore:
    def __init__(self, path: Path, vault: Vault | None = None):
        self.path = path
        self.vault = vault or default_vault()
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, str]]:
        try:
            data = json.loads(self.vault.read_text(self.path) or "[]")
        except ValueError:
            return []
        return (
            [c for c in data if isinstance(c, dict) and c.get("name")]
            if isinstance(data, list)
            else []
        )

    def save(self, name: str, phone: str = "", email: str = "") -> dict[str, str]:
        name = " ".join(name.split())[:60]
        with self._lock:
            contacts = [c for c in self.load() if _norm(c["name"]) != _norm(name)]
            old = next((c for c in self.load() if _norm(c["name"]) == _norm(name)), {})
            contact = {
                "name": name,
                "phone": phone or old.get("phone", ""),
                "email": email or old.get("email", ""),
            }
            contacts.append(contact)
            self.vault.write_text(self.path, json.dumps(contacts, ensure_ascii=False, indent=1))
            return contact

    def delete(self, name: str) -> bool:
        with self._lock:
            contacts = self.load()
            kept = [c for c in contacts if _norm(c["name"]) != _norm(name)]
            if len(kept) == len(contacts):
                return False
            self.vault.write_text(self.path, json.dumps(kept, ensure_ascii=False, indent=1))
            return True

    def find(self, name: str) -> list[dict[str, str]]:
        wanted = _norm(name)
        contacts = self.load()
        same = [c for c in contacts if _norm(c["name"]) == wanted]
        if same:
            return same
        words = wanted.split()
        contains = [c for c in contacts if all(w in _norm(c["name"]).split() for w in words)]
        if contains:
            return contains
        close = [
            c
            for c in contacts
            if difflib.SequenceMatcher(None, wanted, _norm(c["name"])).ratio() >= 0.85
        ]
        return close


def save_contact(store: ContactStore, name: str, phone: str = "", email: str = "") -> ToolResult:
    if not name.strip():
        return ToolResult(False, "The contact needs a name.")
    number = clean_phone(phone) if phone else ""
    if number is None:
        return ToolResult(
            False, "That phone number does not look right. Use digits with the country code."
        )
    contact = store.save(name, number or "", email.strip())
    shown = f" +{contact['phone']}" if contact["phone"] else ""
    return ToolResult(
        True, f"Saved {contact['name']}{shown}{' ' + contact['email'] if contact['email'] else ''}."
    )


def list_contacts(store: ContactStore) -> ToolResult:
    contacts = store.load()
    if not contacts:
        return ToolResult(True, "No contacts saved in Rishu yet.")
    lines = [
        f"- {c['name']}: {'+' + c['phone'] if c['phone'] else 'no number'}{' · ' + c['email'] if c['email'] else ''}"
        for c in contacts
    ]
    return ToolResult(True, "Contacts in Rishu:\n" + "\n".join(lines))


def resolve(store: ContactStore, to: str) -> tuple[dict[str, str] | None, str]:
    """(contact, problem). A phone number given directly is used as is."""
    number = clean_phone(to) if any(ch.isdigit() for ch in to) else None
    if number:
        return {"name": f"+{number}", "phone": number, "email": ""}, ""
    found = store.find(to)
    if not found:
        return (
            None,
            f"'{to}' is not in Rishu's contacts. Ask the user for the WhatsApp number and save it with save_contact.",
        )
    if len(found) > 1:
        return (
            None,
            f"'{to}' could be: {', '.join(c['name'] for c in found[:5])}. Ask the user which one.",
        )
    contact = found[0]
    if not contact.get("phone"):
        return None, f"{contact['name']} has no WhatsApp number in Rishu. Ask the user for it."
    return contact, ""


def describe(store: ContactStore, args: dict[str, Any]) -> str:
    contact, problem = resolve(store, str(args.get("to", "")))
    who = (
        f"{contact['name']} (+{contact['phone']})"
        if contact
        else f"{args.get('to', '')} ({problem})"
    )
    return f'Send on WhatsApp to {who}: "{args.get("text", "")}"'
