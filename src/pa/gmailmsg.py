"""Decoding Gmail's MIME payloads into flat, printable dictionaries.

Gmail returns a recursive ``payload`` tree with base64url bodies. This module
flattens it: pull the headers we care about, find the best body part, and list
attachments. Keeping it separate from the command layer means it is unit
testable without touching the network.
"""

from __future__ import annotations

import base64
import html
import re
from email.utils import parseaddr

INTERESTING_HEADERS = ("From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID", "Reply-To")


def decode_b64(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except Exception:
        return ""
    return raw.decode("utf-8", errors="replace")


def headers_of(payload: dict) -> dict[str, str]:
    """Case-insensitive header lookup flattened to a plain dict."""
    result = {}
    for header in payload.get("headers", []) or []:
        name = header.get("name", "")
        for wanted in INTERESTING_HEADERS:
            if name.lower() == wanted.lower():
                result[wanted] = header.get("value", "")
    return result


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk(part: dict):
    yield part
    for child in part.get("parts", []) or []:
        yield from _walk(child)


def extract_body(payload: dict) -> str:
    """Best-effort plain text: prefer text/plain, else de-tagged text/html."""
    plain, rich = [], []
    for part in _walk(payload or {}):
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        if mime == "text/plain":
            plain.append(decode_b64(data))
        elif mime == "text/html":
            rich.append(decode_b64(data))
    if plain:
        return "\n".join(plain).strip()
    if rich:
        return strip_html("\n".join(rich))
    return ""


def extract_attachments(payload: dict) -> list[dict]:
    found = []
    for part in _walk(payload or {}):
        filename = part.get("filename")
        body = part.get("body") or {}
        if filename and body.get("attachmentId"):
            found.append({
                "filename": filename,
                "mime_type": part.get("mimeType"),
                "size": body.get("size"),
                "attachment_id": body["attachmentId"],
            })
    return found


def summarise(message: dict) -> dict:
    """One-line-per-message shape used by `search` and thread listings."""
    payload = message.get("payload", {}) or {}
    head = headers_of(payload)
    labels = message.get("labelIds", []) or []
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": head.get("From", ""),
        "from_name": parseaddr(head.get("From", ""))[0] or parseaddr(head.get("From", ""))[1],
        "to": head.get("To", ""),
        "subject": head.get("Subject", "(no subject)"),
        "date": head.get("Date", ""),
        "snippet": html.unescape(message.get("snippet", "") or ""),
        "labels": labels,
        "unread": "UNREAD" in labels,
        "starred": "STARRED" in labels,
    }


def detail(message: dict) -> dict:
    """Full shape used by `read`: summary plus body and attachments."""
    payload = message.get("payload", {}) or {}
    record = summarise(message)
    record["body"] = extract_body(payload)
    record["attachments"] = extract_attachments(payload)
    record["message_id_header"] = headers_of(payload).get("Message-ID", "")
    record["cc"] = headers_of(payload).get("Cc", "")
    record["reply_to"] = headers_of(payload).get("Reply-To", "")
    return record
