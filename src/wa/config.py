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


def _settings_path():
    return Path.home() / ".config" / "pa" / "wa.json"


def own_phone() -> str | None:
    """The account holder's own number, needed for code-based pairing."""
    if os.environ.get("WA_PHONE"):
        return os.environ["WA_PHONE"]
    import json

    try:
        return json.loads(_settings_path().read_text()).get("own_phone")
    except (OSError, ValueError):
        return None


def save_own_phone(phone: str) -> None:
    import json

    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    data["own_phone"] = phone
    path.write_text(json.dumps(data, indent=2) + "\n")
