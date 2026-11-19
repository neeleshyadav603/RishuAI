"""Start the local server: ``rishu-core --serve``.

The app starts this process, passes the session token in the ``RISHU_TOKEN``
environment variable and reads one line from stdout:

    RISHU_READY {"port": 51234, "protocol": 1, "version": "0.1.0"}

The same line is also written to the file named in ``RISHU_READY_FILE`` (when
set), because a windowless process may have no usable stdout.

With ``--exit-with-parent`` the core stops when the app is gone: it watches the
process id in ``RISHU_PARENT_PID`` when given, otherwise it waits for stdin to
close. No core is left running alone after the app exits or crashes.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
import time
from collections.abc import Callable
from typing import Any, TextIO

from .. import __version__
from ..config import Settings, load_settings
from .app import create_app
from .runtime import MIN_TOKEN_LENGTH, PROTOCOL_VERSION, CoreRuntime

HOST = "127.0.0.1"  # loopback only: never reachable from the network
READY_PREFIX = "RISHU_READY "


def bind_socket(port: int = 0) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, port))
    sock.listen(16)
    sock.setblocking(False)
    return sock


def _watch_parent(stdin: Any, on_gone: Callable[[], None]) -> None:
    """Block until stdin closes (the parent app is gone), then stop the server."""
    try:
        while stdin.read(1024):
            pass
    except (OSError, ValueError):
        pass
    on_gone()


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(
            0x00100000 | 0x1000, False, pid
        )  # SYNCHRONIZE | QUERY_LIMITED
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watch_pid(pid: int, on_gone: Callable[[], None], interval: float = 1.0) -> None:
    while _pid_alive(pid):
        time.sleep(interval)
    on_gone()


def ensure_streams(log_path: Any) -> None:
    """A windowless process has no stdout/stderr: send them to a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        handle = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        handle = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def build_server(runtime: CoreRuntime) -> Any:
    import uvicorn

    config = uvicorn.Config(
        create_app(runtime),
        log_level="warning",
        access_log=False,
        loop="asyncio",
        http="h11",
        lifespan="off",
        ws_max_size=1_000_000,
    )
    return uvicorn.Server(config)


def serve(
    port: int = 0,
    *,
    settings: Settings | None = None,
    exit_with_parent: bool = False,
    out: TextIO | None = None,
) -> int:
    out = out or sys.stdout
    token = os.environ.get("RISHU_TOKEN", "")
    generated = not token
    if generated:
        token = secrets.token_urlsafe(32)
    elif len(token) < MIN_TOKEN_LENGTH:
        print("RISHU_TOKEN is too short.", file=sys.stderr)
        return 2
    runtime = CoreRuntime(settings or load_settings(), token=token)
    from ..voice.hotkey import start_hotkey

    runtime.hotkey_enabled = start_hotkey(runtime.hotkey_pressed)
    sock = bind_socket(port)
    server = build_server(runtime)

    ready: dict[str, Any] = {
        "port": sock.getsockname()[1],
        "protocol": PROTOCOL_VERSION,
        "version": __version__,
    }
    if generated:
        # Started by hand (development): show the token so a client can connect.
        ready["token"] = token
    line = READY_PREFIX + json.dumps(ready)
    try:
        print(line, file=out, flush=True)
    except (OSError, ValueError, AttributeError):
        pass  # no usable stdout; the ready file below still works
    ready_file = os.environ.get("RISHU_READY_FILE")
    if ready_file:
        temp = ready_file + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(line + "\n")
        os.replace(temp, ready_file)

    parent_pid = os.environ.get("RISHU_PARENT_PID", "")
    if exit_with_parent and parent_pid.isdigit():

        def parent_exited() -> None:
            server.should_exit = True
            time.sleep(3.0)
            os._exit(0)

        threading.Thread(
            target=_watch_pid, args=(int(parent_pid), parent_exited), daemon=True
        ).start()
    elif exit_with_parent:

        def parent_gone() -> None:
            server.should_exit = True
            time.sleep(3.0)
            os._exit(0)  # a turn stuck in a network call must not keep the core alive

        threading.Thread(
            target=_watch_parent, args=(sys.stdin.buffer, parent_gone), daemon=True
        ).start()

    server.run(sockets=[sock])
    return 0
