"""Global shortcut (Windows): Ctrl+Shift+Space starts or stops listening from any app."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
SW_RESTORE = 9


def bring_app_to_front(title: str = "Rishu") -> None:
    """Show the Rishu window (the hotkey owner may take the foreground)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.FindWindowW("FLUTTER_RUNNER_WIN32_WINDOW", title)
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
    except (OSError, AttributeError):
        pass


def start_hotkey(callback: Callable[[], None]) -> bool:
    """Register the shortcut on a background thread. False when not possible."""
    if sys.platform != "win32":
        return False
    registered = threading.Event()
    failed = threading.Event()

    def run() -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE):
            failed.set()  # another app already owns this shortcut
            return
        registered.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    callback()
                except Exception:  # noqa: BLE001, S110 - never kill the hotkey thread
                    pass

    threading.Thread(target=run, name="rishu-hotkey", daemon=True).start()
    for _ in range(20):
        if registered.wait(0.05) or failed.is_set():
            break
    return registered.is_set()
