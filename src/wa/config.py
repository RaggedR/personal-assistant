"""Where the bridge lives, and how to reach it.

Everything is overridable by environment variable so the tests never touch the
real store, and so a relocated checkout does not require a code change.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_BRIDGE_DIR = Path.home() / "git" / "whatsapp-mcp" / "whatsapp-bridge"
DEFAULT_API_BASE = "http://localhost:8080/api"


def bridge_dir() -> Path:
    return Path(os.environ.get("WA_BRIDGE_DIR", DEFAULT_BRIDGE_DIR)).expanduser()


def messages_db() -> Path:
    """Path to the SQLite store the bridge writes incoming messages into."""
    override = os.environ.get("WA_MESSAGES_DB")
    if override:
        return Path(override).expanduser()
    return bridge_dir() / "store" / "messages.db"


def api_base() -> str:
    return os.environ.get("WA_API_BASE", DEFAULT_API_BASE).rstrip("/")


def bridge_binary() -> Path:
    return bridge_dir() / "whatsapp-bridge"
