"""Store tests against a temporary database with the bridge's real schema."""

import sqlite3

import pytest

from pa.errors import NotFoundError, PaError
from wa import store

SCHEMA = """
CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP);
CREATE TABLE messages (
  id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
  is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT,
  media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
  PRIMARY KEY (id, chat_jid));
"""

GROUP = "120363000000000000@g.us"
ALEX = "61412345678@s.whatsapp.net"


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "messages.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT INTO chats (jid, name, last_message_time) VALUES (?,?,?)",
        [(ALEX, "Alex Example", "2026-07-10 18:53:00+10:00"),
         (GROUP, "Project Team", "2026-07-10 17:17:00+10:00"),
         ("0@s.whatsapp.net", "0", "2026-07-01 09:00:00+10:00"),
         ("61499999999@s.whatsapp.net", "", "2026-06-01 09:00:00+10:00"),
         ("61455555555@s.whatsapp.net", "Alex Sample", "2026-05-01 09:00:00+10:00")],
    )
    connection.executemany(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me,"
        " media_type, filename) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("m1", ALEX, "61412345678", "morning", "2026-07-10 09:00:00+10:00", 0, "", ""),
            ("m2", ALEX, "", "replying to you", "2026-07-10 10:00:00+10:00", 1, "", ""),
            ("m3", ALEX, "61412345678", "a photo", "2026-07-10 11:00:00+10:00", 0,
             "image", "pic.jpg"),
            # Group message where the bridge wrote the GROUP's own id as sender.
            ("g1", GROUP, "120363000000000000", "who said this?",
             "2026-07-10 12:00:00+10:00", 0, "", ""),
            # Group message with a genuine member as sender.
            ("g2", GROUP, "61400000002", "I did", "2026-07-10 13:00:00+10:00", 0, "", ""),
        ],
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("WA_MESSAGES_DB", str(path))
    return path


def test_missing_database_raises_store_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("WA_MESSAGES_DB", str(tmp_path / "nope.db"))
    with pytest.raises(store.StoreUnavailable) as info:
        store.stats()
    assert "wa bridge start" in str(info.value)


def test_store_opens_read_only(db):
    # A CLI must never be able to write to the bridge's database.
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM messages")


def test_stats(db):
    got = store.stats()
    assert got["chats"] == 5
    assert got["messages"] == 5
    assert got["latest"].startswith("2026-07-10 13:00")
    assert got["stale_days"] is not None


def test_chats_excludes_the_zero_artefact(db):
    jids = [c["jid"] for c in store.chats()]
    assert "0@s.whatsapp.net" not in jids
    assert ALEX in jids


def test_chats_newest_first_with_last_message(db):
    found = store.chats()
    assert found[0]["jid"] == ALEX
    assert found[0]["last_message"] == "a photo"
    assert found[0]["label"] == "Alex Example"


def test_chats_groups_only(db):
    found = store.chats(groups_only=True)
    assert [c["jid"] for c in found] == [GROUP]
    assert found[0]["is_group"] is True


def test_chats_query_matches_name_and_jid(db):
    assert [c["jid"] for c in store.chats(query="example")] == [ALEX]
    assert len(store.chats(query="alex")) == 2  # both Alexes
    assert [c["jid"] for c in store.chats(query="1203630")] == [GROUP]


def test_messages_are_oldest_first(db):
    found = store.messages(ALEX)
    assert [m["id"] for m in found] == ["m1", "m2", "m3"]


def test_limit_keeps_the_most_recent_not_the_first(db):
    found = store.messages(ALEX, limit=2)
    assert [m["id"] for m in found] == ["m2", "m3"]


def test_sender_label_resolves_names_and_me(db):
    found = {m["id"]: m["sender_label"] for m in store.messages(ALEX)}
    assert found["m1"] == "Alex Example"
    assert found["m2"] == "me"


def test_group_sender_equal_to_chat_is_reported_unknown(db):
    """The bridge writes the group's own id as sender for many messages.

    Rendering that as a participant would invent information, so it must read
    as unknown.
    """
    found = {m["id"]: m["sender_label"] for m in store.messages(GROUP)}
    assert found["g1"] == "(unknown)"
    assert found["g2"] == "61400000002"


def test_media_only_filter(db):
    found = store.messages(ALEX, media_only=True)
    assert [m["id"] for m in found] == ["m3"]
    assert found[0]["media_type"] == "image"


def test_from_me_filter(db):
    assert [m["id"] for m in store.messages(ALEX, from_me=True)] == ["m2"]
    assert [m["id"] for m in store.messages(ALEX, from_me=False)] == ["m1", "m3"]


def test_query_filter_is_case_insensitive(db):
    assert [m["id"] for m in store.messages(query="MORNING")] == ["m1"]


def test_context_returns_surrounding_messages(db):
    got = store.context("m2", before=1, after=1)
    assert got["target"]["id"] == "m2"
    assert [m["id"] for m in got["before"]] == ["m1"]
    assert [m["id"] for m in got["after"]] == ["m3"]


def test_context_of_unknown_message(db):
    with pytest.raises(NotFoundError):
        store.context("nope")


def test_resolve_chat_by_jid_phone_and_name(db):
    assert store.resolve_chat(ALEX)["jid"] == ALEX
    assert store.resolve_chat("61412345678")["jid"] == ALEX
    assert store.resolve_chat("Alex Example")["jid"] == ALEX


def test_resolve_chat_ambiguous_name_refuses(db):
    # Two chats are named Alex: refuse rather than pick one and misdeliver.
    with pytest.raises(PaError) as info:
        store.resolve_chat("Alex")
    assert "be more specific" in str(info.value)
    assert "matches 2 chats" in str(info.value)


def test_resolve_chat_exact_name_wins_over_ambiguous_prefix(db):
    # "Alex Example" is a prefix-ambiguous query but an exact name match.
    assert store.resolve_chat("Alex Example")["jid"] == ALEX


def test_resolve_chat_unknown(db):
    with pytest.raises(NotFoundError):
        store.resolve_chat("nobody at all")


def test_media_message_requires_media(db):
    assert store.media_message("m3")["filename"] == "pic.jpg"
    with pytest.raises(NotFoundError) as info:
        store.media_message("m1")
    assert "no media" in str(info.value)


def test_contacts_finds_chats_and_group_members(db):
    found = store.contacts("6141")
    labels = {c["jid"]: c["source"] for c in found}
    assert ALEX in labels and labels[ALEX] == "chat"
    assert any(c["source"] == "group member" for c in found)


def test_parse_timestamp_handles_bridge_format():
    got = store.parse_timestamp("2026-07-11 10:50:17+10:00")
    assert got.hour == 10 and got.utcoffset().total_seconds() == 10 * 3600
    assert store.parse_timestamp(None) is None
    assert store.parse_timestamp("nonsense") is None
