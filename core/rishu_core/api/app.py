"""The local HTTP + WebSocket API the Rishu app talks to (spec §4, §12.3).

Only reachable on 127.0.0.1, and every request must carry the session token
that the app created when it started this core. Requests that come from a web
page (they carry an ``Origin`` header) are refused, so a site open in the
user's browser cannot talk to Rishu.
"""

from __future__ import annotations

import asyncio
import hmac
import json
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .. import __version__
from ..activity_log import ActivityLog
from .runtime import PROTOCOL_VERSION, CoreRuntime, UnknownProvider
from .session import Session

MAX_FRAME_CHARS = 64_000


def _token_ok(runtime: CoreRuntime, header: str | None) -> bool:
    scheme, _, value = (header or "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(
        value.strip().encode(), runtime.token.encode()
    )


def create_app(runtime: CoreRuntime) -> FastAPI:
    app = FastAPI(title="Rishu core", version=__version__, docs_url=None, redoc_url=None)
    app.openapi_url = None
    app.state.runtime = runtime

    def authorized(request: Request) -> None:
        if request.headers.get("origin"):
            raise HTTPException(status_code=403, detail="browser requests are not allowed")
        if not _token_ok(runtime, request.headers.get("authorization")):
            raise HTTPException(status_code=401, detail="missing or wrong session token")

    guard = [Depends(authorized)]

    @app.exception_handler(UnknownProvider)
    async def unknown_provider(request: Request, exc: UnknownProvider) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "unknown provider"})

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "name": "rishu-core", "version": __version__, "protocol": PROTOCOL_VERSION}

    @app.get("/v1/settings", dependencies=guard)
    async def get_settings() -> dict[str, Any]:
        return {
            "settings": runtime.public_settings(),
            "providers": runtime.providers(),
            "secure_store": runtime.secrets.kind,
            "keys_persist": bool(runtime.secrets.persistent),
        }

    @app.put("/v1/settings", dependencies=guard)
    async def put_settings(request: Request) -> dict[str, Any]:
        patch = await _json_object(request)
        try:
            settings = runtime.update_settings(patch)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"settings": settings}

    @app.put("/v1/providers/{name}/key", dependencies=guard)
    async def put_key(name: str, request: Request) -> dict[str, Any]:
        body = await _json_object(request)
        key = body.get("api_key")
        if not isinstance(key, str):
            raise HTTPException(status_code=422, detail="api_key must be text")
        try:
            runtime.set_api_key(name, key)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"providers": runtime.providers(), "keys_persist": bool(runtime.secrets.persistent)}

    @app.delete("/v1/providers/{name}/key", dependencies=guard)
    async def delete_key(name: str) -> dict[str, Any]:
        runtime.delete_api_key(name)
        return {"providers": runtime.providers()}

    @app.post("/v1/providers/{name}/test", dependencies=guard)
    async def test_provider(name: str, request: Request) -> dict[str, Any]:
        body = await _json_object(request, allow_empty=True)
        key = body.get("api_key")
        if key is not None and not isinstance(key, str):
            raise HTTPException(status_code=422, detail="api_key must be text")
        return await asyncio.to_thread(runtime.test_provider, name, key)

    @app.get("/v1/activity", dependencies=guard)
    async def activity(limit: int = 50) -> dict[str, Any]:
        log = ActivityLog(runtime.home / "activity.jsonl")
        return {"entries": log.tail(max(1, min(limit, 500)))}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if websocket.headers.get("origin") or not _token_ok(
            runtime, websocket.headers.get("authorization")
        ):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await _serve_connection(runtime, websocket)

    return app


async def _json_object(request: Request, allow_empty: bool = False) -> dict[str, Any]:
    raw = await request.body()
    if not raw and allow_empty:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="body must be JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    return data


async def _serve_connection(runtime: CoreRuntime, websocket: WebSocket) -> None:
    loop = asyncio.get_running_loop()
    outbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def send(event: dict[str, Any]) -> None:
        """Thread-safe: the agent thread hands events to the connection."""
        try:
            loop.call_soon_threadsafe(outbox.put_nowait, event)
        except RuntimeError:
            pass  # the loop is closing; the connection is gone anyway

    async def pump() -> None:
        while True:
            event = await outbox.get()
            if event is None:
                return
            await websocket.send_text(json.dumps(event, ensure_ascii=False))

    session = Session(runtime, send)
    sender = asyncio.create_task(pump())
    turns: set[asyncio.Task[None]] = set()
    max_chars = int(runtime.server_option("max_message_chars", 8000))
    send(runtime.hello())
    try:
        while True:
            raw = await websocket.receive_text()
            event = _parse_frame(raw)
            if event is None:
                session.error("bad_frame", "That message was not a valid Rishu event.")
                continue
            kind = event.get("type")
            if kind == "user_message":
                text = event.get("text")
                if not isinstance(text, str) or not text.strip():
                    session.error("bad_frame", "user_message needs text.")
                elif len(text) > max_chars:
                    session.error("too_long", f"Messages can be up to {max_chars} characters.")
                elif not session.try_begin_turn():
                    session.error("busy", "Rishu is still working on the previous message.")
                else:
                    task = asyncio.create_task(asyncio.to_thread(session.run_turn, text.strip()))
                    turns.add(task)
                    task.add_done_callback(turns.discard)
            elif kind == "stop":
                session.stop()
            elif kind == "approval_response":
                call_id, approved = event.get("call_id"), event.get("approved")
                if isinstance(call_id, str) and isinstance(approved, bool):
                    session.approval(call_id, approved, event.get("always_allow") is True)
                else:
                    session.error("bad_frame", "approval_response needs call_id and approved.")
            elif kind == "new_conversation":
                session.new_conversation()
            else:
                session.error("unsupported", f"Event '{kind}' is not supported by this core.")
    except WebSocketDisconnect:
        pass
    finally:
        session.close()
        outbox.put_nowait(None)
        try:
            await asyncio.wait_for(sender, timeout=1.0)
        except Exception:  # noqa: BLE001 - the socket is already closed
            sender.cancel()


def _parse_frame(raw: str) -> dict[str, Any] | None:
    if len(raw) > MAX_FRAME_CHARS:
        return None
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("v") != PROTOCOL_VERSION:
        return None
    if not isinstance(event.get("type"), str):
        return None
    return event
