"""PROTECTED MODULE (spec §5 "Secrets", §6): where API keys are kept.

Secrets are never written to disk in plain text:

- Windows: encrypted with DPAPI (tied to the Windows user account) and stored
  in the data folder.
- Other desktops (development): the system keyring, when one is installed.
- Otherwise: memory only, for this run. The caller tells the user.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

MAX_SECRET_LENGTH = 512
_SERVICE = "Rishu"
# Extra entropy mixed into DPAPI, so other programs' generic unprotect calls
# on a copied blob do not work by accident. Not a secret by itself.
_ENTROPY = b"rishu-core/secrets/v1"


def clean_secret(value: str) -> str:
    """Trim a pasted key and reject anything that cannot be a key."""
    value = value.strip()
    if not value:
        raise ValueError("the key is empty")
    if len(value) > MAX_SECRET_LENGTH:
        raise ValueError("the key is too long")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("the key contains spaces or control characters")
    return value


class SecretStore(Protocol):
    kind: str  # "dpapi" | "keyring" | "memory"
    persistent: bool

    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class MemoryStore:
    """Keeps secrets for this run only."""

    kind = "memory"
    persistent = False

    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._items.get(name)

    def set(self, name: str, value: str) -> None:
        self._items[name] = value

    def delete(self, name: str) -> None:
        self._items.pop(name, None)


# ---- Windows DPAPI ---------------------------------------------------------


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    """Encrypt or decrypt ``data`` for the current Windows user."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.restype = wintypes.BOOL
    source, entropy, result = blob(data), blob(_ENTROPY), Blob()
    ui_forbidden = 0x1  # CRYPTPROTECT_UI_FORBIDDEN: never show a dialog
    ok = function(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        ui_forbidden,
        ctypes.byref(result),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI call failed")  # type: ignore[attr-defined]
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


class DpapiStore:
    """Secrets encrypted with Windows DPAPI in ``<data folder>/secrets.json``."""

    kind = "dpapi"
    persistent = True

    def __init__(self, path: Path, codec: Any = None):
        self.path = path
        # ``codec(data, protect=bool)`` is injectable so the file logic is testable anywhere.
        self._codec = codec or _dpapi
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temp, self.path)

    def get(self, name: str) -> str | None:
        with self._lock:
            encoded = self._load().get(name)
        if not isinstance(encoded, str):
            return None
        try:
            return self._codec(base64.b64decode(encoded), protect=False).decode("utf-8")
        except (OSError, ValueError):
            return None  # written by another Windows user, or damaged

    def set(self, name: str, value: str) -> None:
        encoded = base64.b64encode(self._codec(value.encode("utf-8"), protect=True)).decode()
        with self._lock:
            data = self._load()
            data[name] = encoded
            self._save(data)

    def delete(self, name: str) -> None:
        with self._lock:
            data = self._load()
            if data.pop(name, None) is not None:
                self._save(data)


# ---- System keyring (non-Windows development machines) ----------------------


class KeyringStore:
    kind = "keyring"
    persistent = True

    def __init__(self, backend: Any):
        self._backend = backend

    def get(self, name: str) -> str | None:
        try:
            return self._backend.get_password(_SERVICE, name)
        except Exception:  # noqa: BLE001 - any backend failure means "not available"
            return None

    def set(self, name: str, value: str) -> None:
        self._backend.set_password(_SERVICE, name, value)

    def delete(self, name: str) -> None:
        try:
            self._backend.delete_password(_SERVICE, name)
        except Exception:  # noqa: BLE001 - deleting a missing secret is fine
            pass


def _working_keyring() -> Any | None:
    try:
        import keyring  # type: ignore[import-not-found]

        backend = keyring.get_keyring()
        if getattr(backend, "priority", 0) <= 0:  # the "fail" and "null" backends
            return None
        return keyring
    except Exception:  # noqa: BLE001 - keyring is optional
        return None


def open_secret_store(home: Path, platform: str | None = None) -> SecretStore:
    """The best store this machine offers."""
    if (platform or sys.platform) == "win32":
        return DpapiStore(home / "secrets.json")
    backend = _working_keyring()
    if backend is not None:
        return KeyringStore(backend)
    return MemoryStore()
