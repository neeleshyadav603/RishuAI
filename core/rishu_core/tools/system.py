"""Computer controls (Windows): volume, screenshot, lock, battery."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .registry import ToolResult

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002
CREATE_NO_WINDOW = 0x08000000

PressKey = Callable[[int], None]


def _press_key(vk: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


class SystemControls:
    def __init__(
        self,
        *,
        platform: str = sys.platform,
        press: PressKey | None = None,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        lock: Callable[[], bool] | None = None,
        battery: Callable[[], tuple[int, bool] | None] | None = None,
        pictures: Path | None = None,
    ):
        self.platform = platform
        self._press = press or _press_key
        self._run = run
        self._lock = lock or self._lock_windows
        self._battery = battery or self._battery_windows
        self.pictures = pictures or Path.home() / "Pictures" / "Rishu"

    def _windows_only(self) -> ToolResult | None:
        if self.platform != "win32":
            return ToolResult(False, "This control works on Windows only.")
        return None

    def volume(self, action: str, steps: int = 5) -> ToolResult:
        if problem := self._windows_only():
            return problem
        keys = {"up": VK_VOLUME_UP, "down": VK_VOLUME_DOWN, "mute": VK_VOLUME_MUTE}
        vk = keys.get(action)
        if vk is None:
            return ToolResult(False, "Use action up, down or mute.")
        count = 1 if action == "mute" else max(1, min(int(steps), 25))
        for _ in range(count):
            self._press(vk)
        if action == "mute":
            return ToolResult(True, "Toggled mute.")
        return ToolResult(
            True, f"Volume {'raised' if action == 'up' else 'lowered'} by about {count * 2}%."
        )

    def screenshot(self) -> ToolResult:
        if problem := self._windows_only():
            return problem
        self.pictures.mkdir(parents=True, exist_ok=True)
        path = self.pictures / f"screenshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
        script = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size);"
            "$bmp.Save($args[0],[System.Drawing.Imaging.ImageFormat]::Png)"
        )
        try:
            result = self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"& {{{script}}}",
                    str(path),
                ],
                capture_output=True,
                timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(False, f"Screenshot failed: {type(exc).__name__}")
        if result.returncode != 0 or not path.exists():
            return ToolResult(False, "Screenshot failed.")
        return ToolResult(True, f"Screenshot saved: {path}", data={"path": str(path)})

    def lock_pc(self) -> ToolResult:
        if problem := self._windows_only():
            return problem
        return (
            ToolResult(True, "Locked the computer.")
            if self._lock()
            else ToolResult(False, "Could not lock.")
        )

    def battery(self) -> ToolResult:
        if problem := self._windows_only():
            return problem
        status = self._battery()
        if status is None:
            return ToolResult(True, "This computer has no battery (or it is not reported).")
        percent, charging = status
        return ToolResult(True, f"Battery: {percent}%{' and charging' if charging else ''}.")

    @staticmethod
    def _lock_windows() -> bool:
        import ctypes

        return bool(ctypes.windll.user32.LockWorkStation())  # type: ignore[attr-defined]

    @staticmethod
    def _battery_windows() -> tuple[int, bool] | None:
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", wintypes.BYTE),
                ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE),
                ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        status = Status()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):  # type: ignore[attr-defined]
            return None
        percent = status.BatteryLifePercent & 0xFF
        if percent == 255 or (status.BatteryFlag & 0xFF) == 128:  # unknown / no battery
            return None
        return percent, status.ACLineStatus == 1
