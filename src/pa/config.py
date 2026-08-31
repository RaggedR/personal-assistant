"""Filesystem layout and per-account configuration.

Layout under ``~/.config/pa`` (override with ``PA_HOME``)::

    client.json                  OAuth client shared by all accounts (optional)
    config.json                  {"default_account": "...", "timezone": "..."}
    accounts/<name>/client.json  per-account OAuth client (optional override)
    accounts/<name>/token.json   refresh token for <name>

Accounts are keyed by a short local nickname ("default", "kodamai"), not by
email address, so that the same code works before we know the address.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_ACCOUNT = "default"

# Credential directories written by the @gongrzhe MCP servers. We read these as
# a fallback so that an existing MCP user works with zero setup, and we never
# write to them.
LEGACY_MCP_DIRS = {
    "gmail": Path.home() / ".gmail-mcp",
    "calendar": Path.home() / ".calendar-mcp",
}


def pa_home() -> Path:
    return Path(os.environ.get("PA_HOME", Path.home() / ".config" / "pa"))


def account_dir(account: str) -> Path:
    return pa_home() / "accounts" / account


def token_path(account: str) -> Path:
    return account_dir(account) / "token.json"


def client_path(account: str) -> Path:
    """Per-account OAuth client, falling back to the shared one."""
    specific = account_dir(account) / "client.json"
    return specific if specific.exists() else pa_home() / "client.json"


def config_path() -> Path:
    return pa_home() / "config.json"


def read_json(path: Path) -> dict | None:
    try:
        with path.open() as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: dict, *, private: bool = False) -> None:
    """Write JSON atomically, 0600 when it holds a secret."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    if private:
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def load_config() -> dict:
    return read_json(config_path()) or {}


def save_config(cfg: dict) -> None:
    write_json(config_path(), cfg)


def resolve_account(explicit: str | None = None) -> str:
    """Account precedence: --account flag, PA_ACCOUNT, config file, "default"."""
    if explicit:
        return explicit
    env = os.environ.get("PA_ACCOUNT")
    if env:
        return env
    return load_config().get("default_account", DEFAULT_ACCOUNT)


def list_accounts() -> list[str]:
    root = pa_home() / "accounts"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "token.json").exists())


def default_timezone() -> str:
    """Timezone for interpreting bare datetimes like ``2026-09-01 14:00``."""
    cfg = load_config()
    if cfg.get("timezone"):
        return cfg["timezone"]
    if os.environ.get("TZ"):
        return os.environ["TZ"]
    # macOS/Linux: /etc/localtime symlinks into the zoneinfo tree.
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return "UTC"
