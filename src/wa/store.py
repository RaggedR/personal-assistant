"""Read-only queries against the bridge's SQLite store.

The bridge is the only writer. We open with ``mode=ro`` so this CLI can never
take a write lock or corrupt the store, however badly it is invoked.

Timestamps are stored as text like ``2026-07-11 10:50:17+10:00``. Comparing
those as strings is *almost* right and fails exactly at a daylight-saving
boundary, where ``+11:00`` sorts after ``+10:00`` for an earlier instant. So
range filters compare ``strftime('%s', timestamp)`` instead, which SQLite
evaluates against the offset. With a few thousand rows the lost index is
irrelevant; a silently mis-ordered message list would not be.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from pa.errors import NotFoundError, PaError

from . import config, jid as jidmod


class StoreUnavailable(PaError):
    """The message database is missing — usually the bridge has never run."""

    exit_code = 6


def _connect() -> sqlite3.Connection:
    path = config.messages_db()
    if not path.exists():
        raise StoreUnavailable(
            f"No message database at {path}.\n"
            "The WhatsApp bridge has never run, or WA_BRIDGE_DIR points elsewhere.\n"
            "Start it with:  wa bridge start"
        )
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse the bridge's timestamp format into an aware datetime."""
    if not value:
        return None
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


EPOCH = "CAST(strftime('%s', {col}) AS INTEGER)"


def _range_clause(column: str, after: datetime | None, before: datetime | None
                  ) -> tuple[str, list]:
    clauses, params = [], []
    if after:
        clauses.append(f"{EPOCH.format(col=column)} >= ?")
        params.append(int(after.timestamp()))
    if before:
        clauses.append(f"{EPOCH.format(col=column)} <= ?")
        params.append(int(before.timestamp()))
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def stats() -> dict:
    """Counts and freshness — the basis of ``wa status``."""
    with _connect() as connection:
        # MAX/MIN on the raw text would compare strings, which is wrong across a
        # daylight-saving change; order by the instant and take the end rows.
        newest = "ORDER BY CAST(strftime('%s', timestamp) AS INTEGER)"
        row = connection.execute(
            "SELECT (SELECT COUNT(*) FROM chats)    AS chats,"
            "       (SELECT COUNT(*) FROM messages) AS messages,"
            f"      (SELECT timestamp FROM messages {newest} DESC LIMIT 1) AS latest,"
            f"      (SELECT timestamp FROM messages {newest} ASC  LIMIT 1) AS earliest"
        ).fetchone()
    latest = parse_timestamp(row["latest"])
    return {
        "database": str(config.messages_db()),
        "chats": row["chats"],
        "messages": row["messages"],
        "earliest": row["earliest"],
        "latest": row["latest"],
        "stale_days": (
            (datetime.now(tz=latest.tzinfo) - latest).days if latest else None
        ),
    }


def _chat_row(row: sqlite3.Row) -> dict:
    name = row["name"] if "name" in row.keys() else None
    record = {
        "jid": row["jid"],
        "name": name or "",
        "label": jidmod.describe(row["jid"], name),
        "is_group": jidmod.is_group(row["jid"]),
        "last_message_time": row["last_message_time"],
    }
    if "last_message" in row.keys():
        record["last_message"] = row["last_message"]
        record["last_is_from_me"] = bool(row["last_is_from_me"])
    return record


def chats(limit: int = 30, query: str | None = None, *, groups_only: bool = False,
          include_last_message: bool = True) -> list[dict]:
    sql = ["SELECT c.jid, c.name, c.last_message_time"]
    if include_last_message:
        sql.append(""", (SELECT content FROM messages m WHERE m.chat_jid = c.jid
                          ORDER BY CAST(strftime('%s', m.timestamp) AS INTEGER) DESC LIMIT 1) AS last_message
                    , (SELECT is_from_me FROM messages m WHERE m.chat_jid = c.jid
                          ORDER BY CAST(strftime('%s', m.timestamp) AS INTEGER) DESC LIMIT 1) AS last_is_from_me""")
    # A chat whose entire local part is "0" is an artefact of the bridge, not a
    # real conversation; it only ever adds noise to a listing.
    sql.append("FROM chats c WHERE c.jid NOT LIKE '0@%'")
    params: list = []
    if query:
        sql.append("AND (LOWER(c.name) LIKE ? OR c.jid LIKE ?)")
        params += [f"%{query.lower()}%", f"%{query}%"]
    if groups_only:
        sql.append(f"AND c.jid LIKE '%@{jidmod.GROUP_SUFFIX}'")
    sql.append("ORDER BY CAST(strftime('%s', c.last_message_time) AS INTEGER) DESC LIMIT ?")
    params.append(limit)

    with _connect() as connection:
        rows = connection.execute(" ".join(sql), params).fetchall()
    return [_chat_row(row) for row in rows]


def get_chat(chat_jid: str) -> dict:
    with _connect() as connection:
        row = connection.execute(
            "SELECT jid, name, last_message_time FROM chats WHERE jid = ?", (chat_jid,)
        ).fetchone()
    if not row:
        raise NotFoundError(f"No chat with JID {chat_jid}")
    return _chat_row(row)


def resolve_chat(value: str) -> dict:
    """Find a chat from a JID, a phone number, or a name fragment.

    Raises if a name fragment is ambiguous — sending to the wrong person is
    the failure mode worth being pedantic about.
    """
    if jidmod.is_jid(value):
        return get_chat(value)

    digits = "".join(ch for ch in value if ch.isdigit())
    if digits and digits == "".join(value.split()).lstrip("+"):
        return get_chat(jidmod.normalise(value))

    matches = chats(limit=10, query=value, include_last_message=False)
    if not matches:
        raise NotFoundError(f"No chat matching {value!r}")
    exact = [m for m in matches if m["name"].lower() == value.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(matches) > 1:
        listing = "\n".join(f"  {m['label']}  {m['jid']}" for m in matches)
        raise PaError(
            f"{value!r} matches {len(matches)} chats — be more specific or pass "
            f"the JID:\n{listing}"
        )
    return matches[0]


def sender_names() -> dict[str, str]:
    """Map bare phone numbers to contact names, from the chats table.

    The bridge stores ``messages.sender`` as a bare number with no ``@domain``,
    while ``chats.jid`` is fully qualified, so the two need reconciling.
    """
    with _connect() as connection:
        rows = connection.execute(
            "SELECT jid, name FROM chats WHERE name IS NOT NULL AND name != ''"
        ).fetchall()
    return {row["jid"].partition("@")[0]: row["name"] for row in rows}


def _sender_label(sender: str, chat_jid: str, from_me: bool,
                  names: dict[str, str] | None) -> str:
    """Best honest label for who sent a message.

    The bridge has a known defect: for many *group* messages it records the
    group's own id as the sender rather than the member who spoke. Rendering
    that as if it were a person invents information, so it is labelled unknown
    instead.

    This applies to groups only. In a one-to-one chat the sender's number
    equalling the chat id is not a defect, it is the normal case.
    """
    if from_me:
        return "me"
    if not sender:
        return "(unknown)"
    number = sender.partition("@")[0]
    if jidmod.is_group(chat_jid) and number == chat_jid.partition("@")[0]:
        return "(unknown)"
    return (names or {}).get(number) or jidmod.describe(sender) or sender


def _message_row(row: sqlite3.Row, chat_names: dict[str, str] | None = None,
                 names: dict[str, str] | None = None) -> dict:
    chat_jid = row["chat_jid"]
    sender = row["sender"] or ""
    from_me = bool(row["is_from_me"])
    return {
        "id": row["id"],
        "chat_jid": chat_jid,
        "chat_name": (chat_names or {}).get(chat_jid, ""),
        "sender": sender,
        "sender_label": _sender_label(sender, chat_jid, from_me, names),
        "from_me": from_me,
        "timestamp": row["timestamp"],
        "content": row["content"] or "",
        "media_type": row["media_type"] or "",
        "filename": row["filename"] or "",
    }


MESSAGE_COLUMNS = ("m.id, m.chat_jid, m.sender, m.content, m.timestamp, "
                   "m.is_from_me, m.media_type, m.filename")


def messages(chat_jid: str | None = None, limit: int = 30, *,
             query: str | None = None, after: datetime | None = None,
             before: datetime | None = None, media_only: bool = False,
             from_me: bool | None = None) -> list[dict]:
    sql = [f"SELECT {MESSAGE_COLUMNS}, c.name AS chat_name",
           "FROM messages m LEFT JOIN chats c ON c.jid = m.chat_jid WHERE 1=1"]
    params: list = []
    if chat_jid:
        sql.append("AND m.chat_jid = ?")
        params.append(chat_jid)
    if query:
        sql.append("AND LOWER(m.content) LIKE ?")
        params.append(f"%{query.lower()}%")
    if media_only:
        sql.append("AND m.media_type IS NOT NULL AND m.media_type != ''")
    if from_me is not None:
        sql.append("AND m.is_from_me = ?")
        params.append(1 if from_me else 0)
    clause, range_params = _range_clause("m.timestamp", after, before)
    if clause:
        sql.append(clause.lstrip())
        params += range_params
    sql.append(f"ORDER BY {EPOCH.format(col='m.timestamp')} DESC LIMIT ?")
    params.append(limit)

    with _connect() as connection:
        rows = connection.execute(" ".join(sql), params).fetchall()

    chat_names = {row["chat_jid"]: (row["chat_name"] or "") for row in rows}
    people = sender_names()
    # Oldest-first reads like a conversation; the SQL fetches newest-first so
    # that LIMIT selects the *most recent* N rather than the first N ever.
    return [_message_row(row, chat_names, people) for row in reversed(rows)]


def context(message_id: str, before: int = 5, after: int = 5) -> dict:
    """The messages surrounding one message, for reading a thread in situ."""
    with _connect() as connection:
        target = connection.execute(
            f"SELECT {MESSAGE_COLUMNS}, c.name AS chat_name "
            "FROM messages m LEFT JOIN chats c ON c.jid = m.chat_jid "
            "WHERE m.id = ?", (message_id,)
        ).fetchone()
        if not target:
            raise NotFoundError(f"No message with id {message_id}")

        chat_jid, stamp = target["chat_jid"], target["timestamp"]
        epoch = EPOCH.format(col="m.timestamp")
        earlier = connection.execute(
            f"SELECT {MESSAGE_COLUMNS} FROM messages m WHERE m.chat_jid = ? "
            f"AND {epoch} < CAST(strftime('%s', ?) AS INTEGER) "
            f"ORDER BY {epoch} DESC LIMIT ?", (chat_jid, stamp, before)
        ).fetchall()
        later = connection.execute(
            f"SELECT {MESSAGE_COLUMNS} FROM messages m WHERE m.chat_jid = ? "
            f"AND {epoch} > CAST(strftime('%s', ?) AS INTEGER) "
            f"ORDER BY {epoch} ASC LIMIT ?", (chat_jid, stamp, after)
        ).fetchall()

    chat_names = {chat_jid: target["chat_name"] or ""}
    people = sender_names()
    return {
        "chat_jid": chat_jid,
        "chat_name": chat_names[chat_jid],
        "before": [_message_row(r, chat_names, people) for r in reversed(earlier)],
        "target": _message_row(target, chat_names, people),
        "after": [_message_row(r, chat_names, people) for r in later],
    }


def contacts(query: str, limit: int = 20) -> list[dict]:
    """Search chats and message senders for a name or number.

    Individual chats carry the contact's name; group members only appear as
    sender JIDs, so both are searched and merged.
    """
    like = f"%{query.lower()}%"
    with _connect() as connection:
        rows = connection.execute(
            "SELECT jid, name, last_message_time FROM chats "
            f"WHERE jid LIKE '%@{jidmod.INDIVIDUAL_SUFFIX}' "
            "AND (LOWER(name) LIKE ? OR jid LIKE ?) "
            "ORDER BY CAST(strftime('%s', last_message_time) AS INTEGER) DESC LIMIT ?",
            (like, f"%{query}%", limit),
        ).fetchall()
        found = {row["jid"]: {"jid": row["jid"], "name": row["name"] or "",
                              "label": jidmod.describe(row["jid"], row["name"]),
                              "source": "chat",
                              "last_seen": row["last_message_time"]}
                 for row in rows}

        remaining = limit - len(found)
        if remaining > 0:
            senders = connection.execute(
                "SELECT DISTINCT sender, MAX(timestamp) AS last_seen FROM messages "
                "WHERE sender LIKE ? AND is_from_me = 0 "
                "GROUP BY sender ORDER BY CAST(strftime('%s', MAX(timestamp)) AS INTEGER) DESC LIMIT ?",
                (f"%{query}%", remaining),
            ).fetchall()
            for row in senders:
                found.setdefault(row["sender"], {
                    "jid": row["sender"], "name": "",
                    "label": jidmod.describe(row["sender"]),
                    "source": "group member", "last_seen": row["last_seen"],
                })
    return list(found.values())


def last_interaction(chat_jid: str) -> dict | None:
    found = messages(chat_jid, limit=1)
    return found[0] if found else None


def media_message(message_id: str) -> dict:
    """Look up a message and confirm it actually carries media."""
    with _connect() as connection:
        row = connection.execute(
            f"SELECT {MESSAGE_COLUMNS} FROM messages m WHERE m.id = ?", (message_id,)
        ).fetchone()
    if not row:
        raise NotFoundError(f"No message with id {message_id}")
    record = _message_row(row)
    if not record["media_type"]:
        raise NotFoundError(f"Message {message_id} has no media attached")
    return record
