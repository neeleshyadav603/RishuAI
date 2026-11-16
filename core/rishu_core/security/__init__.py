"""PROTECTED MODULE (spec §6): secrets now; PIN, biometrics and locking in Phase 3."""

from .secrets import MemoryStore, SecretStore, clean_secret, open_secret_store

__all__ = ["MemoryStore", "SecretStore", "clean_secret", "open_secret_store"]
