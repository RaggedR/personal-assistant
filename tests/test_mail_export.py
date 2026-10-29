"""`pa mail export` must reproduce the message's RFC-822 original byte-for-byte.

The whole point of export over read is fidelity: a saved .eml is only useful
as evidence if its DKIM signature still verifies, and that holds only when the
bytes are the untouched original. So these tests assert exact round-trip,
including Gmail's quirk of returning base64url WITHOUT padding.
"""

import base64

import pytest

from pa import output, services
from pa.cli import build_parser
from pa.commands import mail

# Length not divisible by 3, so the base64 encoding genuinely needs padding —
# which Gmail strips. If cmd_export failed to restore it, decoding would raise.
RAW_ORIGINAL = (
    b"Return-Path: <neil@kodamai.com>\r\n"
    b"DKIM-Signature: v=1; a=rsa-sha256; d=kodamai.com; s=sel;\r\n"
    b"Subject: Re: Continued use of MacBeth\r\n"
    b"\r\n"
    b"body bytes, exactly as received."
)


class Call:
    def __init__(self, name, kwargs, result):
        self.name, self.kwargs, self.result = name, kwargs, result

    def execute(self):
        return self.result


class FakeMessages:
    def get(self, **kw):
        assert kw.get("format") == "raw", "export must request the raw format"
        unpadded = base64.urlsafe_b64encode(RAW_ORIGINAL).decode().rstrip("=")
        return Call("messages.get", kw, {"raw": unpadded})


class FakeUsers:
    def messages(self):
        return FakeMessages()


class FakeGmail:
    def users(self):
        return FakeUsers()


@pytest.fixture
def fake_api(monkeypatch):
    api = FakeGmail()
    monkeypatch.setattr(services, "service", lambda *a, **k: api)
    monkeypatch.setattr(mail, "_api", lambda args: api)
    output.set_json(False)
    return api


def parse(argv):
    return build_parser().parse_args(argv)


def test_export_writes_exact_rfc822_bytes(fake_api, tmp_path):
    out = tmp_path / "msg.eml"
    args = parse(["mail", "export", "1a17cb06eab3260b", "--out", str(out)])
    args.func(args)
    assert out.read_bytes() == RAW_ORIGINAL


def test_export_to_a_directory_uses_the_id_as_filename(fake_api, tmp_path):
    args = parse(["mail", "export", "abc123", "--out", str(tmp_path)])
    args.func(args)
    assert (tmp_path / "abc123.eml").read_bytes() == RAW_ORIGINAL


def test_export_creates_missing_parent_directories(fake_api, tmp_path):
    out = tmp_path / "nested" / "deeper" / "msg.eml"
    args = parse(["mail", "export", "abc123", "--out", str(out)])
    args.func(args)
    assert out.read_bytes() == RAW_ORIGINAL
