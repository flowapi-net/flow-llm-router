"""Persist and load FlowGate's vault master key for auto-unlock."""

from __future__ import annotations

import os
from pathlib import Path

from flowgate.config import Settings


def resolve_master_key_path(settings: Settings) -> Path:
    """Resolve the configured master-key path."""
    configured = settings.security.master_key_path or "~/.flowgate/master.key"
    return Path(configured).expanduser()


def save_master_key(settings: Settings, key: str) -> Path:
    """Save a base64-url Fernet key to disk with owner-only permissions."""
    path = resolve_master_key_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best effort on non-POSIX filesystems.
        pass
    return path


def load_master_key(settings: Settings) -> str | None:
    """Load the persisted master key if present."""
    path = resolve_master_key_path(settings)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def has_master_key(settings: Settings) -> bool:
    """Return True when a persisted master key exists."""
    return resolve_master_key_path(settings).exists()
