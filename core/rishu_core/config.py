"""Locate and load Rishu's configuration, prompts and data folder."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


def find_root() -> Path:
    """Return the folder that holds ``config/`` and ``shared/``.

    Order: RISHU_ROOT env var, a PyInstaller bundle, then the parents of this file.
    """
    env = os.environ.get("RISHU_ROOT")
    if env:
        return Path(env)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle and (Path(bundle) / "config" / "defaults.yaml").exists():
        return Path(bundle)
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "defaults.yaml").exists():
            return parent
    raise FileNotFoundError("Rishu config folder not found. Set RISHU_ROOT.")


def data_dir() -> Path:
    """Per-user folder for Rishu's local data (notes, logs, later the database)."""
    env = os.environ.get("RISHU_HOME")
    if env:
        path = Path(env)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "Rishu"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "Rishu"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "rishu"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@dataclass(frozen=True)
class Settings:
    root: Path
    defaults: dict[str, Any]
    models: dict[str, Any]
    policy: dict[str, Any]
    app_aliases: dict[str, Any]

    def with_defaults(self, overrides: dict[str, Any]) -> Settings:
        """A copy with the user's own settings laid over ``config/defaults.yaml``."""
        return replace(self, defaults={**self.defaults, **overrides})


def load_settings(root: Path | None = None) -> Settings:
    root = root or find_root()
    cfg = root / "config"
    return Settings(
        root=root,
        defaults=load_yaml(cfg / "defaults.yaml"),
        models=load_yaml(cfg / "models.yaml"),
        policy=load_yaml(cfg / "policy.yaml"),
        app_aliases=load_yaml(cfg / "app_aliases.yaml"),
    )


def read_prompt(name: str, root: Path | None = None) -> str:
    """Read ``shared/prompts/<name>.md``."""
    root = root or find_root()
    return (root / "shared" / "prompts" / f"{name}.md").read_text(encoding="utf-8").strip()
