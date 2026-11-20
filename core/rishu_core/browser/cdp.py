"""A small Chrome DevTools Protocol client (one page target, over WebSocket).

A reader thread receives every message: replies are matched to their request
id, events go to the listeners (used by teach mode to collect recorded steps).
"""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Callable
from typing import Any, Protocol


class CdpError(Exception):
    pass


class Socket(Protocol):
    def send(self, message: str) -> None: ...
    def recv(self, timeout: float | None = None) -> str: ...
    def close(self) -> None: ...


def connect_socket(url: str) -> Socket:
    from websockets.sync.client import connect

    # No Origin header: Chrome then accepts the local connection.
    options: dict[str, Any] = {
        "max_size": 64 * 1024 * 1024,
        "open_timeout": 10,
        "origin": None,
        "proxy": None,  # 127.0.0.1: never through a proxy from the environment
        "ping_interval": None,
        "compression": None,
    }
    try:
        return connect(url, legacy=True, **options)  # websockets >= 16: a plain connection
    except TypeError:
        options.pop("proxy")
        return connect(url, **options)


Listener = Callable[[str, dict[str, Any]], None]


class CdpSession:
    def __init__(self, url: str, connect: Callable[[str], Socket] = connect_socket):
        self.url = url
        self._socket = connect(url)
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[threading.Event, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self.closed = False
        self._reader = threading.Thread(target=self._read, name="rishu-cdp", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        while not self.closed:
            try:
                raw = self._socket.recv()
            except Exception:  # noqa: BLE001 - the browser or tab went away
                break
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if "id" in message:
                with self._lock:
                    waiting = self._pending.pop(message["id"], None)
                if waiting is not None:
                    waiting[1].append(message)
                    waiting[0].set()
            elif "method" in message:
                for listener in list(self._listeners):
                    try:
                        listener(message["method"], message.get("params") or {})
                    except Exception:  # noqa: BLE001, S110 - a listener must not stop the reader
                        pass
        self.closed = True
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for event, _ in pending:
            event.set()

    def on_event(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 30
    ) -> dict[str, Any]:
        if self.closed:
            raise CdpError("the browser tab is closed")
        request_id = next(self._ids)
        done, box = threading.Event(), []
        with self._lock:
            self._pending[request_id] = (done, box)
        self._socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        if not done.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise CdpError(f"{method} timed out")
        if not box:
            raise CdpError("the browser tab is closed")
        reply = box[0]
        if "error" in reply:
            raise CdpError(f"{method}: {reply['error'].get('message', 'error')}")
        return reply.get("result") or {}

    def evaluate(self, expression: str, timeout: float = 30) -> Any:
        """Run JavaScript in the page and return its JSON value."""
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
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
        self.closed = True
        try:
            self._socket.close()
        except Exception:  # noqa: BLE001, S110
            pass
