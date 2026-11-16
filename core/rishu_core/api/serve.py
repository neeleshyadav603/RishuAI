"""Start the local server: ``rishu-core --serve``.

The app starts this process, passes the session token in the ``RISHU_TOKEN``
environment variable and reads one line from stdout:

    RISHU_READY {"port": 51234, "protocol": 1, "version": "0.1.0"}

With ``--exit-with-parent`` the core stops as soon as its stdin closes, which
happens when the app exits or crashes, so no core is left running alone.
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
    print(READY_PREFIX + json.dumps(ready), file=out, flush=True)

    if exit_with_parent:

        def parent_gone() -> None:
            server.should_exit = True
            time.sleep(3.0)
            os._exit(0)  # a turn stuck in a network call must not keep the core alive

        threading.Thread(
            target=_watch_parent, args=(sys.stdin.buffer, parent_gone), daemon=True
        ).start()

    server.run(sockets=[sock])
    return 0
