"""Rishu's own offline model: llama.cpp's server (MIT) with a small open model.

The server program ships with the Windows installer (``core/local-llm``).
The model file is downloaded once, when the user asks for it, from Hugging
Face (Apache-2.0 Qwen3 GGUF; which one is in config/models.yaml). It runs on
the CPU, needs no key and has no daily limit; the router uses it when the
free online keys are missing, exhausted or offline.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

CREATE_NO_WINDOW = 0x08000000
HF = "https://huggingface.co"


def bundled_server() -> Path | None:
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    here = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[3]
    )
    for candidate in (here / "local-llm" / name, here / "dist" / "rishu-core" / "local-llm" / name):
        if candidate.exists():
            return candidate
    found = shutil.which("llama-server")
    return Path(found) if found else None


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class LocalModel:
    def __init__(
        self,
        home: Path,
        cfg: Mapping[str, Any],
        *,
        server: Callable[[], Path | None] = bundled_server,
        http: httpx.Client | None = None,
        spawn: Callable[..., Any] = subprocess.Popen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.folder = home / "models"
        self.cfg = dict(cfg or {})
        self._server = server
        self._http = http or httpx.Client(timeout=30, follow_redirects=True)
        self._spawn = spawn
        self._sleep = sleep
        self._download_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._process: Any = None
        self._url: str | None = None
        self.choice = str(self.cfg.get("default", "small"))
        self.progress: dict[str, Any] | None = None
        self.error = ""
        self.listeners: list[Callable[[dict[str, Any]], None]] = []

    # ---- what is chosen and what is on disk -----------------------------------

    def choices(self) -> dict[str, dict[str, Any]]:
        return dict(self.cfg.get("choices") or {})

    def _spec(self) -> dict[str, Any]:
        choices = self.choices()
        return choices.get(self.choice) or next(iter(choices.values()), {})

    def choose(self, choice: str) -> None:
        if choice in self.choices() and choice != self.choice:
            self.stop()
            self.choice = choice
            self._publish()

    def model_path(self) -> Path | None:
        spec = self._spec()
        prefix = str(spec.get("repo", "")).split("/")[-1].removesuffix("-GGUF")
        suffix = str(spec.get("file_suffix", ".gguf"))
        if not self.folder.is_dir():
            return None
        for path in sorted(self.folder.glob("*.gguf")):
            if path.name.startswith(prefix) and path.name.endswith(suffix):
                return path
        return None

    def status(self) -> dict[str, Any]:
        path = self.model_path()
        spec = self._spec()
        return {
            "type": "local_model",
            "engine": self._server() is not None,
            "choice": self.choice,
            "choices": {k: str(v.get("label", k)) for k, v in self.choices().items()},
            "downloaded": path is not None,
            "size_mb": round(path.stat().st_size / 1e6) if path else int(spec.get("size_mb", 0)),
            "running": self._url is not None
            and self._process is not None
            and self._process.poll() is None,
            "progress": self.progress,
            "error": self.error,
        }

    def _publish(self) -> None:
        event = self.status()
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:  # noqa: BLE001, S110
                pass

    # ---- download ----------------------------------------------------------------

    def _resolve(self) -> tuple[str, int, str]:
        """(file name, size, sha256) of the chosen quantisation, from the Hugging Face API."""
        spec = self._spec()
        repo, suffix = spec["repo"], spec.get("file_suffix", "Q4_K_M.gguf")
        info = self._http.get(f"{HF}/api/models/{repo}", params={"blobs": "true"})
        info.raise_for_status()
        for sibling in info.json().get("siblings", []):
            name = sibling.get("rfilename", "")
            if name.endswith(suffix):
                lfs = sibling.get("lfs") or {}
                return (
                    name,
                    int(lfs.get("size") or sibling.get("size") or 0),
                    str(lfs.get("sha256", "")),
                )
        raise RuntimeError(f"no {suffix} file in {repo}")

    def download(self) -> bool:
        """Blocking. Progress goes to the listeners; the file is checked (size and SHA-256)."""
        if not self._download_lock.acquire(blocking=False):
            return False
        try:
            self.error = ""
            name, size, sha = self._resolve()
            self.folder.mkdir(parents=True, exist_ok=True)
            target = self.folder / name
            if target.exists() and (not size or target.stat().st_size == size):
                return True
            part = target.with_suffix(".part")
            digest = hashlib.sha256()
            done = 0
            self.progress = {"done": 0, "total": size}
            self._publish()
            last = 0.0
            url = f"{HF}/{self._spec()['repo']}/resolve/main/{name}"
            with self._http.stream("GET", url, timeout=httpx.Timeout(30, read=120)) as response:
                response.raise_for_status()
                with part.open("wb") as handle:
                    for chunk in response.iter_bytes(1 << 20):
                        handle.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if time.monotonic() - last > 0.5:
                            last = time.monotonic()
                            self.progress = {"done": done, "total": size}
                            self._publish()
            if (size and done != size) or (sha and digest.hexdigest() != sha):
                part.unlink(missing_ok=True)
                raise RuntimeError("the download was damaged; please try again")
            os.replace(part, target)
            return True
        except (httpx.HTTPError, OSError, RuntimeError, KeyError, ValueError) as exc:
            self.error = f"download failed: {exc}"
            return False
        finally:
            self.progress = None
            self._download_lock.release()
            self._publish()

    def delete(self) -> None:
        self.stop()
        path = self.model_path()
        if path is not None:
            path.unlink(missing_ok=True)
        self._publish()

    # ---- the server ------------------------------------------------------------------

    def ensure(self) -> str | None:
        """Base URL of the running server (started on first use), or None if unavailable."""
        if self.progress is not None:
            return None  # still downloading
        with self._run_lock:
            if self._url and self._process is not None and self._process.poll() is None:
                return self._url
            server, model = self._server(), self.model_path()
            if server is None or model is None:
                return None
            port = _free_port()
            threads = max(2, (os.cpu_count() or 4) // 2)
            args = [
                str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                "--ctx-size", str(int(self.cfg.get("ctx_size", 4096))), "--threads", str(threads),
                "--jinja", "--reasoning-format", "deepseek", "-ngl", "0",
                "--chat-template-kwargs", '{"enable_thinking": false}',
            ]  # fmt: skip
            self._log = log = (self.folder / "server.log").open("ab")
            flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = self._spawn(
                args, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags
            )
            url = f"http://127.0.0.1:{port}"
            for _ in range(240):  # loading a model from disk can take a while on a slow laptop
                if self._process.poll() is not None:
                    self.error = (
                        "the offline model engine stopped while starting (see models/server.log)"
                    )
                    self._process = None
                    return None
                try:
                    if self._http.get(url + "/health", timeout=2).status_code == 200:
                        self._url = url + "/v1"
                        self.error = ""
                        threading.Thread(target=self._publish, daemon=True).start()
                        return self._url
                except httpx.HTTPError:
                    pass
                self._sleep(0.5)
            self.stop()
            self.error = "the offline model did not start in time"
            return None

    def stop(self) -> None:
        process, self._process, self._url = self._process, None, None
        log, self._log = getattr(self, "_log", None), None
        if log is not None:
            log.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:  # noqa: BLE001
                process.kill()
