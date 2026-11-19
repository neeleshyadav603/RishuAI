"""PROTECTED MODULE (spec §6): secrets, PIN / Windows Hello / spoken-password lock."""

from .lock import LockManager, WindowsHello, is_panic_phrase, normalize_phrase
from .secrets import MemoryStore, SecretStore, clean_secret, open_secret_store

__all__ = [
    "LockManager",
    "MemoryStore",
    "SecretStore",
    "WindowsHello",
    "clean_secret",
    "is_panic_phrase",
    "normalize_phrase",
    "open_secret_store",
]
