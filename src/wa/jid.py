"""WhatsApp JID handling.

A JID ("Jabber ID", inherited from WhatsApp's XMPP ancestry) identifies a chat:

    61412345678@s.whatsapp.net     an individual
    123456789-987654321@g.us       a group
    61412345678@lid                a "linked ID", used when a number is hidden

Phone numbers are always full international form with no ``+`` and no leading
zero: Australian ``0412 345 678`` is ``61412345678``. Getting this wrong sends a
message to a stranger, so ambiguous input is rejected rather than guessed at.
"""

from __future__ import annotations

import re

from pa.errors import UsageError

INDIVIDUAL_SUFFIX = "s.whatsapp.net"
GROUP_SUFFIX = "g.us"
KNOWN_SUFFIXES = {INDIVIDUAL_SUFFIX, GROUP_SUFFIX, "lid", "broadcast", "newsletter"}


def is_jid(value: str) -> bool:
    return "@" in (value or "")


def is_group(jid: str) -> bool:
    return (jid or "").endswith("@" + GROUP_SUFFIX)


def normalise(value: str) -> str:
    """Turn user input into a JID, or refuse.

    Accepts an existing JID unchanged, or a full international phone number in
    any punctuation. Rejects anything that could plausibly be a local number,
    because guessing a country code can misdeliver a message.
    """
    if not value or not str(value).strip():
        raise UsageError("Empty recipient")
    text = str(value).strip()

    if is_jid(text):
        local, _, domain = text.partition("@")
        if domain not in KNOWN_SUFFIXES:
            raise UsageError(
                f"Unrecognised JID domain '@{domain}'. Expected one of: "
                + ", ".join(sorted(KNOWN_SUFFIXES))
            )
        if not local:
            raise UsageError(f"Malformed JID: {text!r}")
        return text

    digits = re.sub(r"[^\d]", "", text.lstrip("+"))
    if not digits:
        raise UsageError(f"No digits in recipient {text!r}")
    if text.strip().startswith("0"):
        raise UsageError(
            f"{text!r} looks like a local number. WhatsApp needs the full "
            "international form with no leading zero and no '+' — for example "
            "Australian 0412 345 678 is 61412345678."
        )
    if len(digits) < 8:
        raise UsageError(
            f"{digits!r} is too short to be an international number. Include the "
            "country code, e.g. 61 for Australia."
        )
    return f"{digits}@{INDIVIDUAL_SUFFIX}"


def phone_of(jid: str) -> str:
    """The bare number part of an individual JID; '' for groups."""
    if not jid or is_group(jid):
        return ""
    return jid.partition("@")[0]


def describe(jid: str, name: str | None = None) -> str:
    """Human label: prefer a known name, fall back to the number, note groups."""
    if name and name.strip():
        return f"{name.strip()}{' (group)' if is_group(jid) else ''}"
    if is_group(jid):
        return f"group {jid.partition('@')[0]}"
    return phone_of(jid) or jid
