"""Ordering across a daylight-saving boundary.

The bridge stores timestamps as text with a UTC offset. Sorting that text
lexicographically is almost right, and wrong exactly where the offset changes:
`02:00+10:00` sorts before `02:30+11:00` as a string, but is 30 minutes *later*
as an instant. These tests pin the epoch-based comparison that fixes it.
"""

import sqlite3

import pytest

from wa import store

SCHEMA = """
CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP);
CREATE TABLE messages (
  id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
  is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT,
  media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
  PRIMARY KEY (id, chat_jid));
"""

CHAT = "61412345678@s.whatsapp.net"
# EARLIER is 15:30Z; LATER is 16:00Z. As raw strings the order is reversed.
EARLIER = "2026-04-05 02:30:00+11:00"
LATER = "2026-04-05 02:00:00+10:00"


@pytest.fixture
def dst_db(tmp_path, monkeypatch):
    path = tmp_path / "messages.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO chats VALUES (?,?,?)", (CHAT, "Nick", LATER))
    connection.executemany(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me,"
        " media_type, filename) VALUES (?,?,?,?,?,?,?,?)",
        [("earlier", CHAT, "61412345678", "sent first", EARLIER, 0, "", ""),
         ("later", CHAT, "61412345678", "sent second", LATER, 0, "", "")],
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("WA_MESSAGES_DB", str(path))
    return path


def test_raw_string_sort_really_is_wrong(dst_db):
    # Establishes that the bug being guarded against is real, not hypothetical.
    connection = sqlite3.connect(f"file:{dst_db}?mode=ro", uri=True)
    naive = [r[0] for r in connection.execute(
        "SELECT id FROM messages ORDER BY timestamp ASC")]
    assert naive == ["later", "earlier"]  # wrong: 'later' is the later instant


def test_messages_are_ordered_by_true_instant(dst_db):
    assert [m["id"] for m in store.messages(CHAT)] == ["earlier", "later"]


def test_limit_across_a_dst_boundary_keeps_the_true_latest(dst_db):
    assert [m["id"] for m in store.messages(CHAT, limit=1)] == ["later"]


def test_stats_reports_the_true_latest(dst_db):
    assert store.stats()["latest"] == LATER


def test_context_orders_correctly_across_the_boundary(dst_db):
    got = store.context("later", before=1, after=1)
    assert [m["id"] for m in got["before"]] == ["earlier"]
    assert got["after"] == []
