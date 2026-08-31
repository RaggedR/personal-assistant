"""Talking to the local whatsmeow bridge, and managing its process.

The bridge is a Go program holding a live WhatsApp Web session. It exposes two
POST endpoints, ``/api/send`` and ``/api/download``, and writes incoming
messages into SQLite.

Only the standard library is used here — a personal CLI does not need `requests`
as a dependency for two JSON POSTs.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from pa.errors import ApiError, PaError, UsageError

from . import config

LOG_PATH = Path.home() / ".config" / "pa" / "whatsapp-bridge.log"
PID_PATH = Path.home() / ".config" / "pa" / "whatsapp-bridge.pid"


class BridgeDown(PaError):
    """The bridge is not reachable, so nothing can be sent."""

    exit_code = 6


def _endpoint(path: str) -> str:
    return f"{config.api_base()}/{path.lstrip('/')}"


def port_open(timeout: float = 0.4) -> bool:
    parsed = urlparse(config.api_base())
    host, port = parsed.hostname or "localhost", parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_running(timeout: float = 1.0) -> bool:
    """Confirm the listener really is the bridge, not just anything on the port.

    Both endpoints reject non-POST with 405, so a GET returning 405 is positive
    identification. A 404 or a successful GET means something else is listening.
    """
    if not port_open():
        return False
    request = urllib.request.Request(_endpoint("send"), method="GET")
    try:
        urllib.request.urlopen(request, timeout=timeout)
        return False
    except urllib.error.HTTPError as exc:
        return exc.code == 405
    except OSError:
        return False


def _post(path: str, payload: dict, timeout: float = 60.0) -> dict:
    if not port_open():
        raise BridgeDown(
            "The WhatsApp bridge is not running, so nothing can be sent.\n"
            "Start it with:  wa bridge start\n"
            "Check it with:  wa status"
        )
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        _endpoint(path), data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()
        try:
            detail = json.loads(detail).get("message", detail)
        except json.JSONDecodeError:
            pass
        raise ApiError(f"Bridge rejected the request ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise BridgeDown(f"Could not reach the bridge: {exc}") from exc

    try:
        return json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return {"success": True, "message": body.strip()}


def send(recipient: str, message: str = "", media_path: str | None = None) -> dict:
    """Send a text and/or a file. The bridge treats both through one endpoint."""
    if not message and not media_path:
        raise UsageError("Nothing to send: provide a message or a file")
    payload: dict = {"recipient": recipient, "message": message}
    if media_path:
        path = Path(media_path).expanduser().resolve()
        if not path.exists():
            raise UsageError(f"File not found: {path}")
        # The bridge reads the file itself, so it needs an absolute local path.
        payload["media_path"] = str(path)
    result = _post("send", payload)
    if not result.get("success", True):
        raise ApiError(f"Send failed: {result.get('message', 'no reason given')}")
    return result


def download(message_id: str, chat_jid: str) -> dict:
    result = _post("download", {"message_id": message_id, "chat_jid": chat_jid})
    if not result.get("success", True):
        raise ApiError(f"Download failed: {result.get('message', 'no reason given')}")
    return result


# ------------------------------------------------------------ process control


def _read_pid() -> int | None:
    try:
        pid = int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


CODE_MARKER = "Enter this code in WhatsApp"
SUCCESS_MARKER = "Successfully connected and authenticated"
LOGGED_OUT_MARKER = "Device logged out"


def _extract_pair_code(text: str) -> str | None:
    """Pull the 8-character linking code out of the bridge's output.

    The bridge prints it on its own indented line after CODE_MARKER. Codes look
    like ``ABCD-EFGH``; take the last one, since a retry appends a fresh code.
    """
    import re

    codes = re.findall(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", text)
    return codes[-1] if codes else None


def pair(phone: str, wait_seconds: float = 45.0) -> dict:
    """Start the bridge in phone-number pairing mode and return the link code.

    Phone-number pairing is far better suited to being driven by an agent than
    QR scanning: the code is plain text with a ~3 minute lifetime, where a QR
    is an image that rotates every ~20 seconds. The bridge already supports it
    via the WHATSAPP_PHONE environment variable.

    Returns as soon as the code appears, leaving the bridge running so the
    person has time to enter it. Poll ``is_running`` afterwards to confirm.
    """
    import time

    if is_running():
        return {"already_connected": True}

    binary = config.bridge_binary()
    if not binary.exists():
        raise BridgeDown(
            f"Bridge binary not found at {binary}.\n"
            f"Build it with:  cd {config.bridge_dir()} && go build"
        )

    stop()  # clear any half-started process holding the session
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Truncate so we only read markers from *this* attempt.
    LOG_PATH.write_text("")

    environment = dict(os.environ, WHATSAPP_PHONE=phone)
    with LOG_PATH.open("ab") as log:
        process = subprocess.Popen(
            [str(binary)], cwd=str(config.bridge_dir()),
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, env=environment,
        )
    PID_PATH.write_text(str(process.pid))

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BridgeDown(
                "The bridge exited before printing a pairing code.\n"
                + "\n".join(tail_log(15))
            )
        text = LOG_PATH.read_text(errors="replace")
        code = _extract_pair_code(text) if CODE_MARKER in text else None
        if code:
            return {"code": code, "pid": process.pid, "phone": phone,
                    "log": str(LOG_PATH)}
        if SUCCESS_MARKER in text:
            return {"already_connected": True, "pid": process.pid}
        time.sleep(0.5)

    raise BridgeDown(
        f"No pairing code appeared within {wait_seconds:.0f}s. Recent output:\n"
        + "\n".join(tail_log(20))
    )


def start(foreground: bool = False) -> dict:
    """Launch the bridge.

    The first ever run prints a QR code that must be scanned with the phone, so
    that case needs a terminal. Afterwards the session is stored and it can run
    detached.
    """
    if is_running():
        return {"started": False, "already_running": True, "pid": _read_pid()}

    binary = config.bridge_binary()
    if not binary.exists():
        raise BridgeDown(
            f"Bridge binary not found at {binary}.\n"
            f"Build it with:  cd {config.bridge_dir()} && go build\n"
            "(Requires Go: brew install go)"
        )

    if foreground:
        # Inherit stdio so the QR code is visible and scannable.
        subprocess.run([str(binary)], cwd=str(config.bridge_dir()), check=False)
        return {"started": True, "foreground": True}

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log:
        process = subprocess.Popen(
            [str(binary)], cwd=str(config.bridge_dir()),
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    PID_PATH.write_text(str(process.pid))
    return {"started": True, "pid": process.pid, "log": str(LOG_PATH)}


def stop() -> dict:
    pid = _read_pid()
    if pid is None:
        return {"stopped": False, "reason": "not running"}
    os.kill(pid, signal.SIGTERM)
    PID_PATH.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def tail_log(lines: int = 40) -> list[str]:
    if not LOG_PATH.exists():
        return []
    content = LOG_PATH.read_text(errors="replace").splitlines()
    return content[-lines:]
