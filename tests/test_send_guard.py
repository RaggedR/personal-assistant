"""The send guard is a safety property, so it gets tested like one.

A fake Gmail API records every call, letting us assert the strong claim: when
--confirm is absent, no send request reaches Google at all.
"""

import base64

import pytest

from pa import output, services
from pa.cli import build_parser
from pa.commands import mail
from pa.errors import ConfirmationRequired, UsageError


class Call:
    def __init__(self, log, name, kwargs, result):
        self.log, self.name, self.kwargs, self.result = log, name, kwargs, result

    def execute(self):
        self.log.append((self.name, self.kwargs))
        return self.result


class FakeDrafts:
    def __init__(self, log):
        self.log = log

    def create(self, **kw):
        return Call(self.log, "drafts.create", kw, {"id": "d1", "message": {"id": "m1"}})

    def send(self, **kw):
        return Call(self.log, "drafts.send", kw, {"id": "m1", "threadId": "t1"})

    def delete(self, **kw):
        return Call(self.log, "drafts.delete", kw, {})

    def get(self, **kw):
        raw = base64.urlsafe_b64encode(b"draft body").decode()
        return Call(self.log, "drafts.get", kw, {"message": {
            "id": "m1", "threadId": "t1", "labelIds": [],
            "payload": {
                "headers": [{"name": "To", "value": "alex@example.com"},
                            {"name": "Subject", "value": "Grant"}],
                "parts": [{"mimeType": "text/plain", "body": {"data": raw}}],
            },
        }})


class FakeMessages:
    def __init__(self, log):
        self.log = log

    def send(self, **kw):
        return Call(self.log, "messages.send", kw, {"id": "m9", "threadId": "t9"})

    def trash(self, **kw):
        return Call(self.log, "messages.trash", kw, {"id": "m9"})

    def get(self, **kw):
        return Call(self.log, "messages.get", kw, {
            "id": "m1", "threadId": "t1", "labelIds": [],
            "payload": {"headers": [{"name": "From", "value": "Alex <alex@example.com>"},
                                    {"name": "Subject", "value": "Grant"},
                                    {"name": "Message-ID", "value": "<orig@mail>"}],
                        "parts": []},
        })


class FakeUsers:
    def __init__(self, log):
        self.log = log

    def drafts(self):
        return FakeDrafts(self.log)

    def messages(self):
        return FakeMessages(self.log)


class FakeGmail:
    def __init__(self):
        self.log = []

    def users(self):
        return FakeUsers(self.log)


@pytest.fixture
def fake_api(monkeypatch):
    api = FakeGmail()
    monkeypatch.setattr(services, "service", lambda *a, **k: api)
    monkeypatch.setattr(mail, "_api", lambda args: api)
    output.set_json(False)
    return api


def parse(argv):
    return build_parser().parse_args(argv)


def test_send_without_confirm_raises_and_sends_nothing(fake_api, capsys):
    args = parse(["mail", "send", "--to", "alex@example.com",
                  "--subject", "Hi", "--body", "text"])
    with pytest.raises(ConfirmationRequired) as info:
        args.func(args)
    # The strong assertion: Google never saw a send call.
    assert not any(name.endswith("send") for name, _ in fake_api.log)
    message = str(info.value)
    assert "--confirm" in message
    assert "alex@example.com" in message  # the human can see what would go out


def test_send_with_confirm_actually_sends(fake_api):
    args = parse(["mail", "send", "--to", "alex@example.com",
                  "--subject", "Hi", "--body", "text", "--confirm"])
    args.func(args)
    assert [name for name, _ in fake_api.log] == ["messages.send"]


def test_draft_send_without_confirm_is_also_blocked(fake_api):
    args = parse(["mail", "send", "--draft-id", "d1"])
    with pytest.raises(ConfirmationRequired):
        args.func(args)
    assert not any(name == "drafts.send" for name, _ in fake_api.log)


def test_draft_send_with_confirm_proceeds(fake_api):
    args = parse(["mail", "send", "--draft-id", "d1", "--confirm"])
    args.func(args)
    assert "drafts.send" in [name for name, _ in fake_api.log]


def test_creating_a_draft_needs_no_confirmation(fake_api):
    args = parse(["mail", "draft", "--to", "alex@example.com",
                  "--subject", "Hi", "--body", "text"])
    args.func(args)
    assert [name for name, _ in fake_api.log] == ["drafts.create"]


def test_trash_and_discard_are_confirmation_gated(fake_api):
    for argv, forbidden in (
        (["mail", "trash", "m9"], "messages.trash"),
        (["mail", "discard", "d1"], "drafts.delete"),
    ):
        args = parse(argv)
        with pytest.raises(ConfirmationRequired):
            args.func(args)
        assert forbidden not in [name for name, _ in fake_api.log]


def test_recipients_accept_repeated_and_comma_separated_flags():
    assert mail._addresses(["a@x.com,b@x.com", "c@x.com"]) == \
        ["a@x.com", "b@x.com", "c@x.com"]
    assert mail._addresses(None) == []
    assert mail._addresses(["  a@x.com , "]) == ["a@x.com"]


def test_compose_requires_a_recipient(fake_api):
    args = parse(["mail", "draft", "--subject", "Hi", "--body", "x"])
    with pytest.raises(UsageError):
        args.func(args)


def test_compose_requires_a_body(fake_api):
    args = parse(["mail", "draft", "--to", "a@x.com", "--subject", "Hi"])
    with pytest.raises(UsageError):
        args.func(args)


def test_reply_sets_threading_headers_and_subject(fake_api):
    args = parse(["mail", "draft", "--reply-to-id", "m1", "--body", "replying"])
    body, preview = mail._build_mime(args, fake_api)
    assert body["threadId"] == "t1"
    assert preview["subject"] == "Re: Grant"
    assert preview["to"] == ["alex@example.com"]
    raw = base64.urlsafe_b64decode(body["raw"] + "==").decode()
    assert "In-Reply-To: <orig@mail>" in raw
    assert "References: <orig@mail>" in raw


def test_reply_does_not_double_prefix_an_existing_re_subject(fake_api, monkeypatch):
    original = FakeMessages.get

    def get_with_re(self, **kw):
        call = original(self, **kw)
        call.result["payload"]["headers"][1]["value"] = "Re: Grant"
        return call

    monkeypatch.setattr(FakeMessages, "get", get_with_re)
    args = parse(["mail", "draft", "--reply-to-id", "m1", "--body", "x"])
    _, preview = mail._build_mime(args, fake_api)
    assert preview["subject"] == "Re: Grant"


def test_header_addresses_ignores_commas_inside_display_names():
    # The bug this guards: naive comma splitting produced two bogus recipients.
    assert mail._header_addresses('"Doe, Jane" <jane@x.com>') == ["jane@x.com"]
    assert mail._header_addresses("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]
    assert mail._header_addresses("") == []
    assert mail._header_addresses(None) == []


def test_reply_prefers_the_reply_to_header(fake_api, monkeypatch):
    original = FakeMessages.get

    def get_with_reply_to(self, **kw):
        call = original(self, **kw)
        call.result["payload"]["headers"].append(
            {"name": "Reply-To", "value": "list@example.org"})
        return call

    monkeypatch.setattr(FakeMessages, "get", get_with_reply_to)
    args = parse(["mail", "draft", "--reply-to-id", "m1", "--body", "x"])
    _, preview = mail._build_mime(args, fake_api)
    assert preview["to"] == ["list@example.org"]


def test_body_file_is_read_from_disk(fake_api, tmp_path):
    path = tmp_path / "body.txt"
    path.write_text("from a file")
    args = parse(["mail", "draft", "--to", "a@x.com", "--subject", "S",
                  "--body-file", str(path)])
    _, preview = mail._build_mime(args, fake_api)
    assert preview["body"] == "from a file"


def test_missing_body_file_is_a_usage_error(fake_api, tmp_path):
    args = parse(["mail", "draft", "--to", "a@x.com", "--subject", "S",
                  "--body-file", str(tmp_path / "nope.txt")])
    with pytest.raises(UsageError):
        args.func(args)


def test_missing_attachment_is_a_usage_error(fake_api, tmp_path):
    args = parse(["mail", "draft", "--to", "a@x.com", "--subject", "S",
                  "--body", "b", "--attach", str(tmp_path / "nope.pdf")])
    with pytest.raises(UsageError):
        args.func(args)


def test_attachment_is_embedded_in_the_mime_payload(fake_api, tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    args = parse(["mail", "draft", "--to", "a@x.com", "--subject", "S",
                  "--body", "see attached", "--attach", str(path)])
    body, preview = mail._build_mime(args, fake_api)
    raw = base64.urlsafe_b64decode(body["raw"] + "==").decode(errors="replace")
    assert "report.pdf" in raw
    assert preview["attachments"] == ["report.pdf"]
