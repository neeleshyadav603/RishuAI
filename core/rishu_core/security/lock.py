"""PROTECTED MODULE (spec §6): locking Rishu.

When a PIN is set, Rishu starts locked and locks again after a period without
use, or at once on the panic phrase ("Rishu lock"). While locked the core
refuses every request except unlocking. Unlock methods:

- PIN (stored only as a salted scrypt hash; repeated failures cause a pause)
- Windows Hello (fingerprint, face or Windows PIN), when the PC has it
- A spoken password (the transcript of a phrase the user enrolled by voice,
  kept in the encrypted secret store); voice can be imitated, so it only
  unlocks and never authorises risky actions
"""

from __future__ import annotations

import difflib
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .secrets import MemoryStore, SecretStore

PHRASE_SECRET = "rishu.lock.phrase"
PIN_MIN, PIN_MAX = 4, 12
MAX_FAILURES = 5
PAUSE_SECONDS = 30
CREATE_NO_WINDOW = 0x08000000

_PANIC = re.compile(
    r"^(?:hey |ok )?(?:rishu|रिशु)[ ,]*(?:lock|lock karo|lock ho jao|band karo|so jao)$|"
    r"^(?:rishu|रिशु)\s*(?:लॉक|लॉक करो|बंद करो|सो जाओ)$",
    re.IGNORECASE,
)


def is_panic_phrase(text: str) -> bool:
    cleaned = re.sub(r"[.!?।,]+$", "", " ".join(text.lower().split()))
    return bool(_PANIC.match(cleaned))


def normalize_phrase(text: str) -> str:
    """Letters and digits of any script, lower case, no spaces or punctuation."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _hash(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


HELLO_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  $task.Wait(-1) | Out-Null
  $task.Result
}
[Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType = WindowsRuntime] | Out-Null
$avail = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])
if ("$avail" -ne 'Available') { Write-Output "unavailable:$avail"; exit 2 }
if ($args[0] -eq 'check') { Write-Output 'available'; exit 0 }
$r = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($args[1])) ([Windows.Security.Credentials.UI.UserConsentVerificationResult])
Write-Output "result:$r"
if ("$r" -eq 'Verified') { exit 0 } else { exit 1 }
"""


class WindowsHello:
    def __init__(
        self,
        script_dir: Path,
        *,
        platform: str = sys.platform,
        run: Callable[..., Any] = subprocess.run,
    ):
        self.script_dir = script_dir
        self.platform = platform
        self._run = run
        self._available: bool | None = None

    def _call(self, mode: str, message: str = "Rishu", timeout: float = 120) -> tuple[int, str]:
        self.script_dir.mkdir(parents=True, exist_ok=True)
        script = self.script_dir / "rishu_hello.ps1"
        if not script.exists() or script.read_text(encoding="utf-8") != HELLO_SCRIPT:
            script.write_text(HELLO_SCRIPT, encoding="utf-8")
        result = self._run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                mode,
                message,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode, (result.stdout or "").strip()

    def known(self) -> bool:
        """The answer so far, without waiting (False until the check finished)."""
        return bool(self._available)

    def prefetch(self, on_done: Callable[[], None] | None = None) -> None:
        """Check in the background, so starting Rishu never waits for PowerShell."""
        if self.platform != "win32" or self._available is not None:
            return

        def check() -> None:
            if self.available() and on_done is not None:
                on_done()

        threading.Thread(target=check, name="rishu-hello-check", daemon=True).start()

    def available(self) -> bool:
        if self.platform != "win32":
            return False
        if self._available is None:
            try:
                code, _ = self._call("check", timeout=30)
                self._available = code == 0
            except (OSError, subprocess.TimeoutExpired):
                self._available = False
        return self._available

    def verify(self, message: str = "Rishu ko unlock karne ke liye pehchaan dikhao") -> bool:
        if not self.available():
            return False
        try:
            code, _ = self._call("verify", message)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return code == 0


class LockManager:
    def __init__(
        self,
        path: Path,
        *,
        hello: WindowsHello | None = None,
        secrets: SecretStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        idle_minutes: float = 10.0,
    ):
        self.path = path
        self.hello = hello
        self.secrets: SecretStore = secrets or MemoryStore()
        self._clock = clock
        self.idle_minutes = idle_minutes
        self._lock = threading.Lock()
        data = self._load()
        self.locked = bool(data.get("pin"))
        self._failures = 0
        self._paused_until = 0.0
        self._last_activity = clock()

    # ---- storage ---------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temp, self.path)

    @staticmethod
    def _record(secret: str) -> dict[str, str]:
        salt = secrets.token_bytes(16)
        return {"salt": salt.hex(), "hash": _hash(secret, salt).hex()}

    @staticmethod
    def _matches(record: dict[str, str] | None, secret: str) -> bool:
        if not record:
            return False
        try:
            expected = bytes.fromhex(record["hash"])
            return hmac.compare_digest(_hash(secret, bytes.fromhex(record["salt"])), expected)
        except (KeyError, ValueError):
            return False

    # ---- status ----------------------------------------------------------

    @property
    def pin_set(self) -> bool:
        return bool(self._load().get("pin"))

    @property
    def phrase_set(self) -> bool:
        return bool(self.pin_set and self.secrets.get(PHRASE_SECRET))

    def status(self) -> dict[str, Any]:
        paused = max(0.0, self._paused_until - self._clock())
        return {
            "locked": self.locked,
            "pin_set": self.pin_set,
            "phrase_set": self.phrase_set,
            "hello": bool(self.hello and self.hello.known()),
            "idle_minutes": self.idle_minutes,
            "paused_seconds": round(paused),
        }

    # ---- setting up ------------------------------------------------------

    def set_pin(self, pin: str, current: str | None = None) -> None:
        if not (pin.isdigit() and PIN_MIN <= len(pin) <= PIN_MAX):
            raise ValueError(f"the PIN must be {PIN_MIN}-{PIN_MAX} digits")
        with self._lock:
            data = self._load()
            if data.get("pin") and not self._matches(data["pin"], current or ""):
                raise PermissionError("the current PIN is wrong")
            data["pin"] = self._record(pin)
            self._save(data)

    def remove_pin(self, current: str) -> None:
        with self._lock:
            data = self._load()
            if data.get("pin") and not self._matches(data["pin"], current):
                raise PermissionError("the current PIN is wrong")
            self._save({})  # the spoken password depends on the PIN being set
            self.secrets.delete(PHRASE_SECRET)
            self.locked = False

    def set_phrase(self, transcript: str) -> None:
        phrase = normalize_phrase(transcript)
        if len(phrase) < 6:
            raise ValueError("the spoken password is too short; say a few words")
        with self._lock:
            data = self._load()
            if not data.get("pin"):
                raise PermissionError("set a PIN first")
            self.secrets.set(PHRASE_SECRET, phrase)

    def remove_phrase(self) -> None:
        with self._lock:
            self.secrets.delete(PHRASE_SECRET)

    # ---- locking and unlocking -----------------------------------------------

    def lock(self) -> bool:
        if not self.pin_set:
            return False
        self.locked = True
        return True

    def touch(self) -> None:
        self._last_activity = self._clock()

    def idle_due(self) -> bool:
        """True when Rishu should lock because nobody used it for a while."""
        if self.locked or not self.pin_set or self.idle_minutes <= 0:
            return False
        return self._clock() - self._last_activity >= self.idle_minutes * 60

    def _attempt(self, ok: bool) -> tuple[bool, str]:
        if ok:
            self.locked = False
            self._failures = 0
            self.touch()
            return True, "unlocked"
        self._failures += 1
        if self._failures >= MAX_FAILURES:
            self._failures = 0
            self._paused_until = self._clock() + PAUSE_SECONDS
            return False, "paused"
        return False, "wrong"

    def _paused(self) -> bool:
        return self._clock() < self._paused_until

    def unlock_pin(self, pin: str) -> tuple[bool, str]:
        if not self.locked:
            return True, "unlocked"
        if self._paused():
            return False, "paused"
        return self._attempt(self._matches(self._load().get("pin"), pin))

    def unlock_phrase(self, transcript: str) -> tuple[bool, str]:
        if not self.locked:
            return True, "unlocked"
        if self._paused():
            return False, "paused"
        stored = self.secrets.get(PHRASE_SECRET)
        if not stored:
            return False, "no_phrase"
        heard = normalize_phrase(transcript)
        ratio = difflib.SequenceMatcher(None, heard, stored).ratio()
        return self._attempt(ratio >= 0.85)

    def unlock_hello(self) -> tuple[bool, str]:
        if not self.locked:
            return True, "unlocked"
        if self.hello is None or not self.hello.available():
            return False, "no_hello"
        return self._attempt(self.hello.verify())
