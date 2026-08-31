"""Credential resolution and the OAuth login flow.

The central idea is that a *service* ("gmail", "calendar", "contacts") declares
the scopes it needs, and ``credentials_for`` finds the best available source
that covers them:

1. ``~/.config/pa/accounts/<account>/token.json`` — our own store.
2. The @gongrzhe MCP credential directories, for the default account only.
3. Nothing — raise ``AuthError`` with instructions.

Source 2 is what makes migration painless: an existing MCP user gets a working
CLI immediately, and can run ``pa auth login`` later to consolidate.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from . import config
from .errors import AuthError

# Scopes per service. gmail.modify covers read, label, draft AND send; it
# deliberately excludes gmail.settings.sharing and permanent deletion.
SCOPES: dict[str, list[str]] = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.settings.basic",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
    ],
    "contacts": [
        # contacts.other.readonly reaches "other contacts" — people you have
        # emailed but never saved, which is where most work addresses live.
        "https://www.googleapis.com/auth/contacts.readonly",
        "https://www.googleapis.com/auth/contacts.other.readonly",
        "https://www.googleapis.com/auth/directory.readonly",
    ],
}

# Requested in one consent screen by `pa auth login`, so a new user makes a
# single trip to the browser rather than three.
ALL_SCOPES: list[str] = sorted({s for group in SCOPES.values() for s in group})

SETUP_HINT = (
    "No credentials for service '{service}'.\n"
    "Run:  pa auth login\n"
    "First-time setup (once per machine) is documented in docs/SETUP.md — you\n"
    "need a Google Cloud OAuth client JSON saved as {client}."
)


def _client_from_file(path: Path) -> dict:
    """Read a Google 'desktop app' OAuth client JSON.

    Google emits the credentials under an ``installed`` key (desktop) or
    ``web`` key; accept either, and also a pre-unwrapped dict.
    """
    data = config.read_json(path)
    if not data:
        raise AuthError(f"OAuth client file missing or unreadable: {path}")
    for key in ("installed", "web"):
        if key in data:
            data = data[key]
            break
    missing = [k for k in ("client_id", "client_secret") if k not in data]
    if missing:
        raise AuthError(f"OAuth client file {path} is missing: {', '.join(missing)}")
    return data


def _credentials_from_parts(client: dict, token: dict, scopes: list[str]) -> Credentials:
    return Credentials(
        token=token.get("access_token") or token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=client.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=scopes,
    )


def _covers(granted: str | list[str] | None, required: list[str]) -> bool:
    """Does a granted scope string/list satisfy every required scope?

    ``https://mail.google.com/`` is Gmail's superset scope, so treat it as
    covering any gmail scope.
    """
    if not granted:
        return False
    have = set(granted.split()) if isinstance(granted, str) else set(granted)
    if "https://mail.google.com/" in have:
        have |= {s for s in ALL_SCOPES if "gmail" in s}
    return all(scope in have for scope in required)


def _legacy_source(service: str, required: list[str]) -> tuple[dict, dict] | None:
    """Credentials from an @gongrzhe MCP directory, if they cover `required`."""
    directory = config.LEGACY_MCP_DIRS.get(service)
    if not directory or not directory.is_dir():
        return None
    token = config.read_json(directory / "credentials.json")
    if not token or not token.get("refresh_token"):
        return None
    if not _covers(token.get("scope"), required):
        return None
    try:
        client = _client_from_file(directory / "gcp-oauth.keys.json")
    except AuthError:
        return None
    return client, token


def describe_source(service: str, account: str | None = None) -> str:
    """Human-readable provenance, for ``pa auth status``. Never raises."""
    account = config.resolve_account(account)
    required = SCOPES[service]
    token = config.read_json(config.token_path(account))
    if token and _covers(token.get("scopes") or token.get("scope"), required):
        return f"pa store ({config.token_path(account)})"
    if account == config.DEFAULT_ACCOUNT and _legacy_source(service, required):
        return f"legacy MCP ({config.LEGACY_MCP_DIRS[service]})"
    return "none"


def credentials_for(service: str, account: str | None = None) -> Credentials:
    """Return refreshed credentials able to call `service`."""
    if service not in SCOPES:
        raise AuthError(f"Unknown service '{service}'")
    account = config.resolve_account(account)
    required = SCOPES[service]

    creds: Credentials | None = None
    persist_to: Path | None = None

    token = config.read_json(config.token_path(account))
    if token and _covers(token.get("scopes") or token.get("scope"), required):
        client = _client_from_file(config.client_path(account))
        creds = _credentials_from_parts(client, token, list(token.get("scopes") or required))
        persist_to = config.token_path(account)
    elif account == config.DEFAULT_ACCOUNT:
        legacy = _legacy_source(service, required)
        if legacy:
            client, legacy_token = legacy
            creds = _credentials_from_parts(client, legacy_token, required)
            # Deliberately no persist_to: we never write into the MCP dirs.

    if creds is None:
        if token:
            raise AuthError(
                f"Credentials for account '{account}' do not include the scopes "
                f"needed for '{service}'.\nRun:  pa auth login --force"
            )
        raise AuthError(SETUP_HINT.format(service=service, client=config.client_path(account)))

    if not creds.valid:
        if not creds.refresh_token:
            raise AuthError("Stored credentials have no refresh token. Run: pa auth login --force")
        try:
            creds.refresh(Request())
        except Exception as exc:  # google-auth raises a variety of types
            raise AuthError(
                f"Token refresh failed ({exc}).\nRun:  pa auth login --force"
            ) from exc
        if persist_to:
            _save_token(persist_to, creds)

    return creds


def _save_token(path: Path, creds: Credentials) -> None:
    config.write_json(
        path,
        {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scopes": list(creds.scopes or []),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        },
        private=True,
    )


def login(account: str | None = None, scopes: list[str] | None = None) -> Credentials:
    """Run the installed-app OAuth flow and persist the result."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    account = config.resolve_account(account)
    scopes = scopes or ALL_SCOPES
    client_file = config.client_path(account)
    if not client_file.exists():
        raise AuthError(
            f"OAuth client JSON not found at {client_file}.\n"
            "See docs/SETUP.md — create a Google Cloud 'Desktop app' OAuth client,\n"
            f"download the JSON, and save it to that path."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes=scopes)
    # port=0 lets the OS pick a free loopback port for the redirect.
    creds = flow.run_local_server(port=0, prompt="consent")
    _save_token(config.token_path(account), creds)
    return creds


def logout(account: str | None = None) -> bool:
    account = config.resolve_account(account)
    path = config.token_path(account)
    if path.exists():
        path.unlink()
        return True
    return False
