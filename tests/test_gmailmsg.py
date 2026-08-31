import base64

from pa import gmailmsg


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(parts=None, headers=None, **extra):
    return {
        "id": "msg1", "threadId": "thr1", "snippet": "a snippet",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {"headers": headers or [], "parts": parts or []},
        **extra,
    }


def test_decode_b64_handles_missing_padding():
    assert gmailmsg.decode_b64(b64("hello world")) == "hello world"
    assert gmailmsg.decode_b64(None) == ""
    assert gmailmsg.decode_b64("!!!not base64!!!") == ""


def test_headers_are_matched_case_insensitively():
    payload = {"headers": [
        {"name": "from", "value": "A <a@x.com>"},
        {"name": "SUBJECT", "value": "Hi"},
        {"name": "X-Irrelevant", "value": "ignore me"},
    ]}
    got = gmailmsg.headers_of(payload)
    assert got["From"] == "A <a@x.com>"
    assert got["Subject"] == "Hi"
    assert "X-Irrelevant" not in got


def test_plain_text_is_preferred_over_html():
    payload = {"parts": [
        {"mimeType": "text/html", "body": {"data": b64("<p>rich</p>")}},
        {"mimeType": "text/plain", "body": {"data": b64("plain wins")}},
    ]}
    assert gmailmsg.extract_body(payload) == "plain wins"


def test_html_is_de_tagged_when_no_plain_part():
    html = "<style>x{}</style><p>Hello</p><br><b>Neil</b> &amp; co"
    payload = {"parts": [{"mimeType": "text/html", "body": {"data": b64(html)}}]}
    body = gmailmsg.extract_body(payload)
    assert "Hello" in body and "Neil" in body and "& co" in body
    assert "<" not in body and "x{}" not in body


def test_body_found_in_deeply_nested_multipart():
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "multipart/related", "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("deep body")}},
            ]},
        ]},
    ]}
    assert gmailmsg.extract_body(payload) == "deep body"


def test_empty_payload_yields_empty_body():
    assert gmailmsg.extract_body({}) == ""
    assert gmailmsg.extract_body(None) == ""


def test_attachments_require_an_attachment_id():
    payload = {"parts": [
        {"filename": "report.pdf", "mimeType": "application/pdf",
         "body": {"attachmentId": "att1", "size": 1234}},
        # Inline body part with a filename but no attachmentId is not an attachment.
        {"filename": "inline.png", "mimeType": "image/png", "body": {"size": 10}},
        {"mimeType": "text/plain", "body": {"data": b64("hi")}},
    ]}
    found = gmailmsg.extract_attachments(payload)
    assert [a["filename"] for a in found] == ["report.pdf"]
    assert found[0]["attachment_id"] == "att1"


def test_summarise_extracts_flags_and_display_name():
    msg = message(headers=[
        {"name": "From", "value": "Neil Ghani <alex@example.com>"},
        {"name": "Subject", "value": "Grant"},
    ])
    got = gmailmsg.summarise(msg)
    assert got["from_name"] == "Neil Ghani"
    assert got["unread"] is True
    assert got["starred"] is False
    assert got["thread_id"] == "thr1"


def test_summarise_falls_back_to_address_when_no_display_name():
    msg = message(headers=[{"name": "From", "value": "bare@example.com"}])
    assert gmailmsg.summarise(msg)["from_name"] == "bare@example.com"


def test_summarise_defaults_missing_subject():
    assert gmailmsg.summarise(message())["subject"] == "(no subject)"


def test_detail_adds_body_and_attachments():
    msg = message(
        parts=[{"mimeType": "text/plain", "body": {"data": b64("the body")}}],
        headers=[{"name": "Message-ID", "value": "<abc@mail>"},
                 {"name": "Cc", "value": "c@x.com"}],
    )
    got = gmailmsg.detail(msg)
    assert got["body"] == "the body"
    assert got["message_id_header"] == "<abc@mail>"
    assert got["cc"] == "c@x.com"
    assert got["attachments"] == []
