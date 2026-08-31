"""Sending is a safety property, so it is tested as one.

A WhatsApp message has no draft folder and cannot be unsent, so the assertion
is the strong one: without --confirm, the bridge is never contacted at all.
"""

import sqlite3

import pytest

from pa import output
from pa.errors import ConfirmationRequired, UsageError
from wa import bridge
from wa.cli import build_parser

SCHEMA = """
CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP);
CREATE TABLE messages (
  id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
  is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT,
  media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
  PRIMARY KEY (id, chat_jid));
"""

ALEX = "61412345678@s.whatsapp.net"
GROUP = "120363000000000000@g.us"


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "messages.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany("INSERT INTO chats VALUES (?,?,?)",
                           [(ALEX, "Alex Example", "2026-07-10 18:53:00+10:00"),
                            (GROUP, "Project Team", "2026-07-10 17:17:00+10:00")])
    connection.commit()
    connection.close()
    monkeypatch.setenv("WA_MESSAGES_DB", str(path))


@pytest.fixture
def calls(monkeypatch):
    """Record every bridge call; fail loudly if one happens when it must not."""
    recorded = []

    def fake_send(recipient, message="", media_path=None):
        recorded.append(("send", recipient, message, media_path))
        return {"success": True, "message": "sent"}

    monkeypatch.setattr(bridge, "send", fake_send)
    monkeypatch.setattr(bridge, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(bridge, "is_running", lambda *a, **k: True)
    output.set_json(False)
    return recorded


def run(argv):
    args = build_parser().parse_args(argv)
    args.func(args)
    return args


def test_send_without_confirm_never_contacts_the_bridge(db, calls):
    with pytest.raises(ConfirmationRequired) as info:
        run(["send", "--to", "Alex Example", "--message", "hello"])
    assert calls == []
    message = str(info.value)
    assert "--confirm" in message
    # The preview must name both the human label and the exact JID, because
    # misdelivery is the failure that matters.
    assert "Alex Example" in message
    assert ALEX in message


def test_send_with_confirm_sends(db, calls):
    run(["send", "--to", "Alex Example", "--message", "hello", "--confirm"])
    assert calls == [("send", ALEX, "hello", None)]


def test_group_send_without_confirm_is_blocked(db, calls):
    with pytest.raises(ConfirmationRequired) as info:
        run(["send", "--to", "Project", "--message", "hi all"])
    assert calls == []
    assert "(group)" in str(info.value)


def test_send_resolves_a_bare_number_with_no_chat_history(db, calls):
    run(["send", "--to", "+61 499 000 111", "--message", "new contact", "--confirm"])
    assert calls == [("send", "61499000111@s.whatsapp.net", "new contact", None)]


def test_send_refuses_a_local_number_rather_than_guessing(db, calls):
    with pytest.raises(UsageError):
        run(["send", "--to", "0412345678", "--message", "x", "--confirm"])
    assert calls == []


def test_send_requires_a_message_or_file(db, calls):
    with pytest.raises(UsageError):
        run(["send", "--to", "Alex Example"])
    assert calls == []


def test_ambiguous_recipient_is_refused_before_sending(db, calls, monkeypatch):
    connection = sqlite3.connect(str(__import__("os").environ["WA_MESSAGES_DB"]))
    connection.execute("INSERT INTO chats VALUES (?,?,?)",
                       ("61455555555@s.whatsapp.net", "Alex Sample",
                        "2026-05-01 09:00:00+10:00"))
    connection.commit()
    connection.close()
    # Two Nicks and no exact match: normalise() then rejects the name outright
    # rather than any chat being picked. Either way, nothing is sent.
    with pytest.raises((ConfirmationRequired, UsageError)):
        run(["send", "--to", "Alex", "--message", "x", "--confirm"])
    assert calls == []


def test_file_send_is_also_gated(db, calls, tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.4")
    with pytest.raises(ConfirmationRequired) as info:
        run(["send", "--to", "Alex Example", "--file", str(path)])
    assert calls == []
    assert "report.pdf" in str(info.value)


def test_bridge_down_is_reported_not_swallowed(db, monkeypatch):
    monkeypatch.setattr(bridge, "port_open", lambda *a, **k: False)
    output.set_json(False)
    with pytest.raises(bridge.BridgeDown):
        run(["send", "--to", "Alex Example", "--message", "x", "--confirm"])
