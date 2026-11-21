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
import threading
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


def _device_ok(runtime: CoreRuntime, header: str | None) -> bool:
    scheme, _, value = (header or "").partition(" ")
    return scheme.lower() == "bearer" and runtime.phone.device_for(value.strip()) is not None


def create_app(runtime: CoreRuntime, remote: bool = False) -> FastAPI:
    """The core's API. ``remote`` is the phone-link app on the LAN (TLS, device tokens)."""
    app = FastAPI(title="Rishu core", version=__version__, docs_url=None, redoc_url=None)
    app.openapi_url = None
    app.state.runtime = runtime
    check = _device_ok if remote else _token_ok

    def authorized(request: Request) -> None:
        if request.headers.get("origin"):
            raise HTTPException(status_code=403, detail="browser requests are not allowed")
        if not check(runtime, request.headers.get("authorization")):
            raise HTTPException(status_code=401, detail="missing or wrong session token")

    guard = [Depends(authorized)]

    @app.exception_handler(UnknownProvider)
    async def unknown_provider(request: Request, exc: UnknownProvider) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "unknown provider"})

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "name": "rishu-core",
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
        }

    def unlocked() -> None:
        if runtime.lock.locked:
            raise HTTPException(status_code=423, detail="Rishu is locked")

    private = [*guard, Depends(unlocked)]

    @app.get("/v1/lock", dependencies=guard)
    async def lock_status() -> dict[str, Any]:
        return await asyncio.to_thread(runtime.lock.status)

    @app.put("/v1/lock/pin", dependencies=private)
    async def set_pin(request: Request) -> dict[str, Any]:
        body = await _json_object(request)
        pin, current = body.get("pin"), body.get("current")
        if not isinstance(pin, str) or (current is not None and not isinstance(current, str)):
            raise HTTPException(status_code=422, detail="pin must be text")
        try:
            await asyncio.to_thread(runtime.lock.set_pin, pin, current)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        runtime.lock_changed()
        return runtime.lock.status()

    @app.post("/v1/lock/remove", dependencies=private)
    async def remove_pin(request: Request) -> dict[str, Any]:
        body = await _json_object(request)
        current = body.get("current")
        if not isinstance(current, str):
            raise HTTPException(status_code=422, detail="current must be text")
        try:
            await asyncio.to_thread(runtime.lock.remove_pin, current)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        runtime.lock_changed()
        return runtime.lock.status()

    @app.delete("/v1/lock/phrase", dependencies=private)
    async def remove_phrase() -> dict[str, Any]:
        runtime.lock.remove_phrase()
        runtime.lock_changed()
        return runtime.lock.status()

    if remote:

        @app.get("/v1/phone/hello")
        async def phone_hello() -> dict[str, Any]:
            return runtime.phone.hello()

        @app.post("/v1/phone/pair")
        async def phone_pair(request: Request) -> dict[str, Any]:
            body = await _json_object(request)
            code, device = body.get("code"), body.get("device", "Phone")
            if not isinstance(code, str) or not isinstance(device, str):
                raise HTTPException(status_code=422, detail="code and device must be text")
            token = await asyncio.to_thread(runtime.phone.pair, code, device)
            if token is None:
                await asyncio.sleep(1.0)  # slow down guessing
                raise HTTPException(status_code=403, detail="wrong or expired code")
            runtime.phone_paired()
            return {"token": token}

    else:

        @app.get("/v1/phone", dependencies=private)
        async def phone_status() -> dict[str, Any]:
            return runtime.phone.status()

        @app.post("/v1/phone/start", dependencies=private)
        async def phone_start() -> dict[str, Any]:
            try:
                info = await asyncio.to_thread(runtime.start_phone_link)
            except Exception as exc:  # noqa: BLE001 - port, certificate or firewall problems
                raise HTTPException(
                    status_code=500, detail=f"could not start the phone link: {exc}"
                ) from exc
            return {
                **runtime.phone.status(),
                "code": info["code"],
                "expires_in": info["expires_in"],
            }

        @app.post("/v1/phone/stop", dependencies=private)
        async def phone_stop() -> dict[str, Any]:
            await asyncio.to_thread(runtime.stop_phone_link)
            return runtime.phone.status()

        @app.delete("/v1/phone/devices/{device_id}", dependencies=private)
        async def phone_remove(device_id: str) -> dict[str, Any]:
            if not runtime.phone.remove(device_id):
                raise HTTPException(status_code=404, detail="no such phone")
            return runtime.phone.status()

    @app.get("/v1/local-model", dependencies=guard)
    async def local_model_status() -> dict[str, Any]:
        return runtime.local.status()

    @app.post("/v1/local-model/download", dependencies=private)
    async def local_model_download() -> dict[str, Any]:
        status = runtime.local.status()
        if not status["engine"]:
            raise HTTPException(
                status_code=409, detail="the offline model engine is not part of this build"
            )
        if status["progress"] is None and not status["downloaded"]:
            threading.Thread(
                target=runtime.local.download, name="rishu-model-download", daemon=True
            ).start()
        return runtime.local.status()

    @app.delete("/v1/local-model", dependencies=private)
    async def local_model_delete() -> dict[str, Any]:
        await asyncio.to_thread(runtime.local.delete)
        return runtime.local.status()

    @app.get("/v1/settings", dependencies=private)
    async def get_settings() -> dict[str, Any]:
        return {
            "settings": runtime.public_settings(),
            "providers": runtime.providers(),
            "secure_store": runtime.secrets.kind,
            "keys_persist": bool(runtime.secrets.persistent),
        }

    @app.put("/v1/settings", dependencies=private)
    async def put_settings(request: Request) -> dict[str, Any]:
        patch = await _json_object(request)
        try:
            settings = runtime.update_settings(patch)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"settings": settings}

    @app.put("/v1/providers/{name}/key", dependencies=private)
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

    @app.delete("/v1/providers/{name}/key", dependencies=private)
    async def delete_key(name: str) -> dict[str, Any]:
        runtime.delete_api_key(name)
        return {"providers": runtime.providers()}

    @app.post("/v1/providers/{name}/test", dependencies=private)
    async def test_provider(name: str, request: Request) -> dict[str, Any]:
        body = await _json_object(request, allow_empty=True)
        key = body.get("api_key")
        if key is not None and not isinstance(key, str):
            raise HTTPException(status_code=422, detail="api_key must be text")
        return await asyncio.to_thread(runtime.test_provider, name, key)

    @app.get("/v1/voice", dependencies=guard)
    async def voice_status() -> dict[str, Any]:
        return await asyncio.to_thread(runtime.voice.status, True)

    @app.get("/v1/activity", dependencies=private)
    async def activity(limit: int = 50) -> dict[str, Any]:
        log = ActivityLog(runtime.home / "activity.jsonl")
        return {"entries": log.tail(max(1, min(limit, 500)))}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if websocket.headers.get("origin") or not check(
            runtime, websocket.headers.get("authorization")
        ):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await _serve_connection(runtime, websocket, remote)

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


async def _serve_connection(
    runtime: CoreRuntime, websocket: WebSocket, remote: bool = False
) -> None:
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

    session = Session(runtime, send, remote=remote)
    sender = asyncio.create_task(pump())
    turns: set[asyncio.Task[None]] = set()
    max_chars = int(runtime.server_option("max_message_chars", 8000))
    send(runtime.hello())
    if runtime.lock.locked:
        session.locked()

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
                elif session.handle_text(text.strip()) != "ok":
                    pass  # locked, or the panic phrase locked Rishu
                elif not session.try_begin_turn():
                    session.error("busy", "Rishu is still working on the previous message.")
                else:
                    task = asyncio.create_task(asyncio.to_thread(session.run_turn, text.strip()))
                    turns.add(task)
                    task.add_done_callback(turns.discard)
            elif kind == "stop":
                session.stop()
            elif kind == "unlock":
                method, pin = event.get("method"), event.get("pin")
                if method == "pin" and isinstance(pin, str) and len(pin) <= 32:
                    await asyncio.to_thread(session.unlock, "pin", pin)
                elif method == "hello":
                    task = asyncio.create_task(asyncio.to_thread(session.unlock, "hello", None))
                    turns.add(task)
                    task.add_done_callback(turns.discard)
                elif method == "voice":
                    task = asyncio.create_task(asyncio.to_thread(session.unlock_by_voice))
                    turns.add(task)
                    task.add_done_callback(turns.discard)
                else:
                    session.error(
                        "bad_frame", "unlock needs method pin (with pin), hello or voice."
                    )
            elif kind == "teach_cancel":
                teach = getattr(runtime.registry, "teach", None)
                if teach is not None:
                    await asyncio.to_thread(teach.cancel)
            elif kind == "forget_skill":
                name, teach = event.get("name"), getattr(runtime.registry, "teach", None)
                if isinstance(name, str) and teach is not None and not runtime.lock.locked:
                    result = await asyncio.to_thread(teach.delete, name)
                    if not result.ok:
                        session.error("no_such_skill", result.content)
            elif kind == "lock":
                if not runtime.lock_now():
                    session.notice_lock_needs_pin()
            elif kind == "enroll_phrase":
                if runtime.lock.locked:
                    session.error("locked", "Unlock Rishu first.")
                else:
                    task = asyncio.create_task(asyncio.to_thread(session.enroll_phrase))
                    turns.add(task)
                    task.add_done_callback(turns.discard)
            elif runtime.lock.locked and kind in ("approval_response", "new_conversation", "speak"):
                session.error("locked", "Rishu is locked.")
            elif kind == "approval_response":
                call_id, approved = event.get("call_id"), event.get("approved")
                if isinstance(call_id, str) and isinstance(approved, bool):
                    pin = event.get("pin") if isinstance(event.get("pin"), str) else None
                    await asyncio.to_thread(
                        session.approval, call_id, approved, event.get("always_allow") is True, pin
                    )
                else:
                    session.error("bad_frame", "approval_response needs call_id and approved.")
            elif kind == "new_conversation":
                session.new_conversation()
            elif kind == "listen_start":
                task = asyncio.create_task(asyncio.to_thread(session.listen))
                turns.add(task)
                task.add_done_callback(turns.discard)
            elif kind == "listen_stop":
                session.listen_stop()
            elif kind == "speak":
                text = event.get("text")
                if isinstance(text, str) and text.strip() and len(text) <= 5000:
                    await asyncio.to_thread(session.speak, text)
                else:
                    session.error("bad_frame", "speak needs text (up to 5000 characters).")
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
