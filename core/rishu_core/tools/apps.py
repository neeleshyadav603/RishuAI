"""Open apps and URLs on the user's computer.

Safety: only a resolved alias, Start-menu shortcut or bare executable name is
launched, never a command line with arguments and never through a shell.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import webbrowser
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from .registry import ToolResult

_SAFE_PUNCTUATION = set(" .+-()&'_")


def is_safe_name(name: str) -> bool:
    """Letters, digits and combining marks of any script plus a little punctuation.

    Rejects path separators, shell metacharacters and anything else that could
    turn an app name into a command. (``\\w`` is not used because it rejects
    the vowel signs of Devanagari and other Indic scripts.)
    """
    if not 1 <= len(name) <= 80:
        return False
    return all(ch in _SAFE_PUNCTUATION or unicodedata.category(ch)[0] in "LMN" for ch in name)


_FILLER = re.compile(r"\b(app|application|program|software)\b", re.IGNORECASE)

# (kind, target): kind is "exe", "uri" (Windows URI scheme), "shortcut" or "macapp".
Resolved = tuple[str, str]
Spawn = Callable[[str, str], None]


def _platform_key(platform: str) -> str:
    if platform == "win32":
        return "windows"
    return "darwin" if platform == "darwin" else "linux"


def start_menu_index() -> dict[str, str]:
    """Map lower-cased Start-menu shortcut names to their paths (Windows only)."""
    roots = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    index: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in (".lnk", ".url", ".appref-ms"):
                continue
            name = path.stem.lower()
            if "uninstall" in name or "readme" in name:
                continue
            index.setdefault(name, str(path))
    return index


def _default_spawn(platform: str) -> Spawn:
    def spawn(kind: str, target: str) -> None:
        if platform == "win32":
            if kind == "exe":
                path = shutil.which(target)
                if path:
                    subprocess.Popen([path], close_fds=True)  # noqa: S603
                    return
            # URI schemes, shortcuts and App Paths names go through the shell
            # association, with no arguments.
            os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
        elif platform == "darwin":
            subprocess.Popen(["open", "-a", target])  # noqa: S603, S607
        else:
            path = shutil.which(target)
            if not path:
                raise FileNotFoundError(target)
            subprocess.Popen([path], start_new_session=True)  # noqa: S603

    return spawn


class AppLauncher:
    def __init__(
        self,
        aliases: Mapping[str, Mapping[str, str]] | None = None,
        *,
        platform: str = sys.platform,
        index: Mapping[str, str] | None = None,
        spawn: Spawn | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.platform = platform
        table = (aliases or {}).get(_platform_key(platform), {}) or {}
        self._aliases = {str(key).lower(): str(value) for key, value in table.items()}
        self._index = dict(index) if index is not None else None
        self._spawn = spawn if spawn is not None else _default_spawn(platform)
        self._which = which

    @property
    def index(self) -> dict[str, str]:
        if self._index is None:
            self._index = start_menu_index() if self.platform == "win32" else {}
        return self._index

    def _alias_kind(self, target: str) -> Resolved:
        if target.endswith(":"):
            return ("uri", target)
        return ("macapp" if self.platform == "darwin" else "exe", target)

    def resolve(self, name: str) -> Resolved | None:
        query = _FILLER.sub(" ", name).strip().strip("\"'.").lower()
        query = re.sub(r"\s+", " ", query)
        if not is_safe_name(query):
            return None
        if query in self._aliases:
            return self._alias_kind(self._aliases[query])
        if query in self.index:
            return ("shortcut", self.index[query])
        names = list(self._aliases) + list(self.index)
        close = difflib.get_close_matches(query, names, n=1, cutoff=0.8)
        if not close:
            # "chrome" should find the shortcut "google chrome".
            close = [n for n in names if re.search(rf"\b{re.escape(query)}\b", n)][:1]
        if close:
            match = close[0]
            if match in self._aliases:
                return self._alias_kind(self._aliases[match])
            return ("shortcut", self.index[match])
        if " " not in query and self._which(query):
            return ("exe", query)
        return None

    def launch(self, name: str) -> ToolResult:
        resolved = self.resolve(name)
        if resolved is None:
            return ToolResult(False, f"I could not find an app called '{name}' on this computer.")
        kind, target = resolved
        try:
            self._spawn(kind, target)
        except OSError as exc:
            return ToolResult(False, f"Could not open '{name}': {type(exc).__name__}")
        return ToolResult(True, f"Opened {name}.", data={"kind": kind, "target": target})


def normalise_url(url: str) -> str | None:
    """Return a safe http(s) URL, or ``None`` if it is not one."""
    url = url.strip()
    if not url or any(ch.isspace() for ch in url):
        return None
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or "." not in parsed.hostname:
        return None
    return url


def open_url(url: str, opener: Callable[[str], bool] = webbrowser.open) -> ToolResult:
    safe = normalise_url(url)
    if safe is None:
        return ToolResult(False, "That is not a web address I can open (only http/https).")
    try:
        opened = opener(safe)
    except Exception as exc:  # noqa: BLE001 - webbrowser raises many types
        return ToolResult(False, f"Could not open the browser: {type(exc).__name__}")
    if opened is False:
        return ToolResult(False, "No web browser is available on this device.")
    return ToolResult(True, f"Opened {safe} in the browser.", data={"url": safe})
