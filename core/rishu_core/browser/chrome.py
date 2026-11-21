"""Rishu's own Chrome (or Edge) window, controlled over the DevTools protocol.

Rishu starts the browser with remote debugging on a separate profile folder
in its data folder. The user signs in to sites once in that window; Rishu
never stores or types passwords. Chrome refuses remote debugging on the
user's default profile, so this separate profile is also what makes it work.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


class BrowserError(Exception):
    pass


def _windows_candidates() -> list[Path]:
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    names = [
        Path("Google/Chrome/Application/chrome.exe"),
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("BraveSoftware/Brave-Browser/Application/brave.exe"),
    ]
    return [Path(root) / name for name in names for root in roots if root]


def find_browser(platform: str | None = None) -> Path | None:
    if (platform or sys.platform) == "win32":
        for path in _windows_candidates():
            if path.exists():
                return path
        return None
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
    ):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ChromeLauncher:
    def __init__(
        self,
        home: Path,
        *,
        browser_path: Callable[[], Path | None] = find_browser,
        spawn: Callable[..., Any] = subprocess.Popen,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        extra_args: list[str] | None = None,
    ):
        self.folder = home / "browser"
        self.extra_args = list(extra_args or [])
        self.profile = self.folder / "profile"
        self._state = self.folder / "state.json"
        self._browser_path = browser_path
        self._spawn = spawn
        self._http = http or httpx.Client(timeout=3, trust_env=False)
        self._sleep = sleep

    # ---- the DevTools HTTP endpoints ------------------------------------------

    def _port(self) -> int | None:
        try:
            return int(json.loads(self._state.read_text(encoding="utf-8"))["port"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _get(self, port: int, path: str, method: str = "GET") -> Any:
        response = self._http.request(method, f"http://127.0.0.1:{port}{path}")
        response.raise_for_status()
        return response.json()

    def alive(self, port: int | None = None) -> bool:
        port = port or self._port()
        if not port:
            return False
        try:
            return "webSocketDebuggerUrl" in self._get(port, "/json/version")
        except (httpx.HTTPError, ValueError):
            return False

    # ---- start -------------------------------------------------------------

    def ensure(self, url: str = "about:blank") -> int:
        """Return the debugging port of Rishu's browser, starting it if needed."""
        port = self._port()
        if port and self.alive(port):
            return port
        exe = self._browser_path()
        if exe is None:
            raise BrowserError("Chrome or Edge is not installed on this computer")
        port = free_port()
        self.profile.mkdir(parents=True, exist_ok=True)
        args = [
            str(exe),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            *self.extra_args,
            url,
        ]
        flags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS
        self._spawn(
            args,
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(160):  # a first start creates the profile: give it up to 40 s
            self._sleep(0.25)
            if self.alive(port):
                self.folder.mkdir(parents=True, exist_ok=True)
                self._state.write_text(json.dumps({"port": port}), encoding="utf-8")
                return port
        raise BrowserError("the browser did not start in time")

    def pages(self, port: int) -> list[dict[str, Any]]:
        targets = self._get(port, "/json/list")
        return [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]

    def new_page(self, port: int, url: str = "about:blank") -> dict[str, Any]:
        return self._get(port, "/json/new?" + quote(url, safe=":/?&=#%"), method="PUT")

    def activate(self, port: int, target_id: str) -> None:
        try:
            self._http.get(f"http://127.0.0.1:{port}/json/activate/{target_id}")
        except httpx.HTTPError:
            pass
