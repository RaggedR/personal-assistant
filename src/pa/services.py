"""Google API client construction.

``cache_discovery=False`` avoids the oauth2client-based file cache, which is
deprecated and emits a warning on every invocation — unacceptable noise for a
tool whose stdout may be parsed.
"""

from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import auth
from .errors import ApiError, NotFoundError

_SPECS = {
    "gmail": ("gmail", "v1"),
    "calendar": ("calendar", "v3"),
    "contacts": ("people", "v1"),
}


def service(name: str, account: str | None = None):
    api, version = _SPECS[name]
    creds = auth.credentials_for(name, account)
    return build(api, version, credentials=creds, cache_discovery=False)


def translate(exc: HttpError) -> Exception:
    """Turn an HttpError into one of our typed errors with a usable message."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        detail = exc.error_details or exc.reason
    except Exception:
        detail = str(exc)
    if status == 404:
        return NotFoundError(f"Not found: {detail}")
    if status == 403:
        return ApiError(f"Permission denied or quota exceeded: {detail}")
    if status == 401:
        return ApiError(f"Authentication rejected: {detail}. Try: pa auth login --force")
    return ApiError(f"Google API error ({status}): {detail}")
