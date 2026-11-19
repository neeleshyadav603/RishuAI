"""Browser shortcuts and message drafts through official links only.

- YouTube and Google results open in the user's browser.
- WhatsApp: the official click-to-chat link (``whatsapp://send`` for the
  desktop app, ``https://wa.me`` otherwise) opens a chat with the text typed in;
  the user picks the contact if no number is given and presses Send.
- Email: a ``mailto:`` draft in the default mail app.
No unofficial APIs, and nothing is sent without the user.
"""

from __future__ import annotations

import os
import re
import sys
import webbrowser
from collections.abc import Callable
from urllib.parse import quote, quote_plus

from .registry import ToolResult

UriOpener = Callable[[str], bool]
_PHONE = re.compile(r"^\+?[0-9][0-9 \-]{6,18}$")
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def default_uri_opener(uri: str) -> bool:
    """Open a URI with its registered app (Windows), else the browser."""
    if sys.platform == "win32":
        try:
            os.startfile(uri)  # type: ignore[attr-defined]  # noqa: S606
            return True
        except OSError:
            return False
    return bool(webbrowser.open(uri))


def whatsapp_app_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"):
            return True
    except OSError:
        return False


def clean_phone(phone: str) -> str | None:
    """Digits with country code, as wa.me needs (Indian 10-digit numbers get 91)."""
    phone = phone.strip()
    if not phone:
        return ""
    if not _PHONE.match(phone):
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits if 10 <= len(digits) <= 15 else None


def youtube(query: str, opener: UriOpener) -> ToolResult:
    query = query.strip()
    if not query:
        return ToolResult(False, "What should I look for on YouTube?")
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    if not opener(url):
        return ToolResult(False, "Could not open the browser.")
    return ToolResult(
        True, f"Opened YouTube results for '{query}'. The user can pick a video.", data={"url": url}
    )


def browser_search(query: str, opener: UriOpener) -> ToolResult:
    query = query.strip()
    if not query:
        return ToolResult(False, "The search is empty.")
    url = "https://www.google.com/search?q=" + quote_plus(query)
    if not opener(url):
        return ToolResult(False, "Could not open the browser.")
    return ToolResult(
        True, f"Opened Google results for '{query}' in the browser.", data={"url": url}
    )


def whatsapp_draft(
    text: str,
    phone: str,
    opener: UriOpener,
    app_installed: Callable[[], bool] = whatsapp_app_installed,
) -> ToolResult:
    text = text.strip()
    if not text:
        return ToolResult(False, "The message is empty.")
    if len(text) > 2000:
        return ToolResult(False, "The message is too long (2000 characters at most).")
    number = clean_phone(phone)
    if number is None:
        return ToolResult(
            False, "That phone number does not look right. Use digits with the country code."
        )
    if app_installed():
        uri = f"whatsapp://send?text={quote(text)}" + (f"&phone={number}" if number else "")
    else:
        uri = (f"https://wa.me/{number}" if number else "https://wa.me/") + f"?text={quote(text)}"
    if not opener(uri):
        return ToolResult(False, "Could not open WhatsApp.")
    who = f"the chat with +{number}" if number else "WhatsApp (the user picks the contact)"
    return ToolResult(
        True,
        f"Opened {who} with the message typed in. It is NOT sent yet: the user presses Send.",
        data={"uri": uri},
    )


def email_draft(to: str, subject: str, body: str, opener: UriOpener) -> ToolResult:
    to = to.strip()
    if to and not _EMAIL.match(to):
        return ToolResult(False, "That email address does not look right.")
    if len(subject) > 300 or len(body) > 5000:
        return ToolResult(False, "The email is too long for a draft link.")
    uri = f"mailto:{quote(to, safe='@.')}?subject={quote(subject)}&body={quote(body)}"
    if not opener(uri):
        return ToolResult(False, "Could not open the mail app.")
    return ToolResult(
        True,
        "Opened an email draft in the mail app. It is NOT sent: the user reviews and sends it.",
    )
