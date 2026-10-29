"""Gmail subcommands.

Safety posture: composing a draft is free, sending is guarded. ``pa mail send``
refuses to act without ``--confirm`` and instead prints exactly what it would
have sent. The intended flow is ``draft`` → show the human → ``send --draft-id``,
which makes "never send without explicit permission" structural rather than
merely advisory.
"""

from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path

from googleapiclient.errors import HttpError

from .. import gmailmsg, output, services
from ..errors import ConfirmationRequired, UsageError

ME = "me"


def _api(args):
    return services.service("gmail", getattr(args, "account", None))


def _get_message(api, message_id: str, fmt: str = "full") -> dict:
    try:
        return api.users().messages().get(userId=ME, id=message_id, format=fmt).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc


def _addresses(raw: list[str] | None) -> list[str]:
    """Accept repeated flags and comma-separated values interchangeably."""
    out = []
    for chunk in raw or []:
        out.extend(part.strip() for part in chunk.split(",") if part.strip())
    return out


def _header_addresses(header_value: str) -> list[str]:
    """Pull bare addresses out of an RFC 5322 header.

    Never split such a header on commas: a display name may legitimately
    contain one (``"Doe, Jane" <jane@x.com>``), which naive splitting turns
    into two invalid recipients.
    """
    return [addr for _name, addr in getaddresses([header_value or ""]) if addr]


def _body_text(args) -> str:
    """Body from --body, --body-file, or stdin when the file is '-'."""
    if getattr(args, "body_file", None):
        if args.body_file == "-":
            import sys

            return sys.stdin.read()
        path = Path(args.body_file).expanduser()
        if not path.exists():
            raise UsageError(f"Body file not found: {path}")
        return path.read_text()
    if args.body is not None:
        return args.body
    raise UsageError("Provide message text with --body or --body-file")


def _build_mime(args, api) -> tuple[dict, dict]:
    """Construct the raw MIME payload plus a preview dict.

    Returns (request_body, preview). The request body is what Gmail wants;
    the preview is what we show a human before sending.
    """
    to = _addresses(args.to)
    if not to and not getattr(args, "reply_to_id", None):
        raise UsageError("At least one --to recipient is required")

    subject = args.subject or ""
    thread_id = None
    extra_headers = {}

    if getattr(args, "reply_to_id", None):
        original = _get_message(api, args.reply_to_id)
        detail = gmailmsg.detail(original)
        thread_id = original.get("threadId")
        if not to:
            # Reply-To wins over From when the sender asked for it.
            to = _header_addresses(detail.get("reply_to") or detail["from"])
        if not subject:
            base = detail["subject"]
            subject = base if base.lower().startswith("re:") else f"Re: {base}"
        if detail["message_id_header"]:
            extra_headers["In-Reply-To"] = detail["message_id_header"]
            extra_headers["References"] = detail["message_id_header"]

    message = EmailMessage()
    message["To"] = ", ".join(to)
    if args.cc:
        message["Cc"] = ", ".join(_addresses(args.cc))
    if args.bcc:
        message["Bcc"] = ", ".join(_addresses(args.bcc))
    message["Subject"] = subject
    for key, value in extra_headers.items():
        message[key] = value
    message.set_content(_body_text(args))

    for spec in getattr(args, "attach", None) or []:
        path = Path(spec).expanduser()
        if not path.exists():
            raise UsageError(f"Attachment not found: {path}")
        message.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=path.name,
        )

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id

    preview = {
        "to": to,
        "cc": _addresses(args.cc),
        "bcc": _addresses(args.bcc),
        "subject": subject,
        "body": _body_text(args),
        "attachments": [Path(p).name for p in (getattr(args, "attach", None) or [])],
        "thread_id": thread_id,
    }
    return body, preview


def _render_preview(preview: dict) -> list[str]:
    lines = [
        "─" * 60,
        f"To:      {', '.join(preview['to'])}",
    ]
    if preview.get("cc"):
        lines.append(f"Cc:      {', '.join(preview['cc'])}")
    if preview.get("bcc"):
        lines.append(f"Bcc:     {', '.join(preview['bcc'])}")
    lines.append(f"Subject: {preview['subject']}")
    if preview.get("attachments"):
        lines.append(f"Attach:  {', '.join(preview['attachments'])}")
    lines += ["─" * 60, preview["body"].rstrip(), "─" * 60]
    return lines


# ---------------------------------------------------------------- read side


def cmd_search(args):
    api = _api(args)
    try:
        listing = api.users().messages().list(
            userId=ME, q=args.query, maxResults=args.limit,
            labelIds=args.label or None,
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    ids = [m["id"] for m in listing.get("messages", [])]
    messages = []
    for message_id in ids:
        messages.append(gmailmsg.summarise(
            _get_message(api, message_id, fmt="metadata")
        ))

    def render(payload):
        if not payload["messages"]:
            return ["No messages matched."]
        rows = [[
            "*" if m["unread"] else " ",
            m["id"],
            output.truncate(m["from_name"], 22),
            output.truncate(m["subject"], 45),
            output.truncate(m["snippet"], 60),
        ] for m in payload["messages"]]
        return output.table(rows, headers=["", "ID", "FROM", "SUBJECT", "SNIPPET"])

    output.emit({"query": args.query, "count": len(messages), "messages": messages}, render)


def cmd_read(args):
    api = _api(args)
    record = gmailmsg.detail(_get_message(api, args.id))
    if args.mark_read:
        api.users().messages().modify(
            userId=ME, id=args.id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def render(m):
        lines = [
            f"From:    {m['from']}",
            f"To:      {m['to']}",
        ]
        if m.get("cc"):
            lines.append(f"Cc:      {m['cc']}")
        lines += [
            f"Date:    {m['date']}",
            f"Subject: {m['subject']}",
            f"Labels:  {', '.join(m['labels'])}",
            f"Ids:     message={m['id']} thread={m['thread_id']}",
        ]
        if m["attachments"]:
            lines.append("Attach:  " + ", ".join(
                f"{a['filename']} ({a['size']}b)" for a in m["attachments"]
            ))
        lines += ["", m["body"] or "(no text body)"]
        return lines

    output.emit(record, render)


def cmd_thread(args):
    api = _api(args)
    try:
        thread = api.users().threads().get(userId=ME, id=args.id, format="full").execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    messages = [gmailmsg.detail(m) for m in thread.get("messages", [])]

    def render(payload):
        lines = [f"Thread {payload['id']} — {len(payload['messages'])} message(s)"]
        for index, m in enumerate(payload["messages"], 1):
            lines += [
                "",
                f"[{index}] {m['from']}  ({m['date']})  id={m['id']}",
                f"    {m['subject']}",
                "",
            ]
            body = m["body"] or "(no text body)"
            limit = None if args.full else 800
            lines += ["    " + ln for ln in body[:limit].splitlines()]
            if limit and len(body) > limit:
                lines.append(f"    … [{len(body) - limit} more chars — use --full]")
        return lines

    output.emit({"id": thread.get("id"), "messages": messages}, render)


def cmd_labels(args):
    api = _api(args)
    items = api.users().labels().list(userId=ME).execute().get("labels", [])
    items.sort(key=lambda label: (label.get("type") != "system", label.get("name", "")))

    def render(payload):
        rows = [[label.get("type", ""), label.get("id", ""), label.get("name", "")]
                for label in payload["labels"]]
        return output.table(rows, headers=["TYPE", "ID", "NAME"])

    output.emit({"labels": items}, render)


def cmd_attachments(args):
    api = _api(args)
    message = _get_message(api, args.id)
    found = gmailmsg.extract_attachments(message.get("payload", {}))
    if not found:
        output.emit({"id": args.id, "attachments": []},
                    lambda _: ["No attachments on this message."])
        return

    saved = []
    if args.download:
        target = Path(args.download).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        for item in found:
            blob = api.users().messages().attachments().get(
                userId=ME, messageId=args.id, id=item["attachment_id"]
            ).execute()
            data = base64.urlsafe_b64decode(blob["data"] + "=" * (-len(blob["data"]) % 4))
            # Guard against a hostile filename escaping the target directory.
            safe = os.path.basename(item["filename"]) or "attachment"
            destination = target / safe
            destination.write_bytes(data)
            saved.append(str(destination))

    def render(payload):
        rows = [[a["filename"], str(a["size"]), a["mime_type"]] for a in payload["attachments"]]
        lines = output.table(rows, headers=["FILENAME", "SIZE", "TYPE"])
        if payload["saved"]:
            lines += ["", "Saved:"] + [f"  {p}" for p in payload["saved"]]
        return lines

    output.emit({"id": args.id, "attachments": found, "saved": saved}, render)


def cmd_export(args):
    """Write the full RFC-822 original of a message to a .eml file.

    Unlike ``read`` (which renders a parsed view) this preserves the message
    exactly as Gmail received it — all headers, the DKIM-Signature and
    Authentication-Results included — so the saved file is the verifiable
    original rather than a transcript. That matters when the .eml is kept as
    evidence: a third party can re-check the DKIM signature against the
    sending domain's key only if nothing was reparsed or re-encoded.
    """
    api = _api(args)
    message = _get_message(api, args.id, fmt="raw")
    data = message["raw"]
    # Gmail returns base64url WITHOUT padding; restore it before decoding.
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    out = Path(args.out).expanduser() if args.out else Path.cwd()
    # A directory target (existing dir, or a trailing slash) gets a stable,
    # collision-free default filename; anything else is taken as the file path.
    if out.is_dir() or args.out in (None, "") or str(args.out).endswith(os.sep):
        out = out / f"{args.id}.eml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)

    output.emit(
        {"id": args.id, "path": str(out), "bytes": len(raw)},
        lambda p: [f"Wrote {p['bytes']} bytes (RFC-822 original) to {p['path']}"],
    )


# --------------------------------------------------------------- write side


def cmd_draft(args):
    api = _api(args)
    body, preview = _build_mime(args, api)
    try:
        draft = api.users().drafts().create(userId=ME, body={"message": body}).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    def render(payload):
        return (["Draft created."] + _render_preview(payload["preview"]) +
                ["", f"Draft id: {payload['draft_id']}",
                 f"Send it with:  pa mail send --draft-id {payload['draft_id']} --confirm"])

    output.emit({"draft_id": draft["id"],
                 "message_id": draft.get("message", {}).get("id"),
                 "preview": preview}, render)


def cmd_drafts(args):
    api = _api(args)
    listing = api.users().drafts().list(userId=ME, maxResults=args.limit).execute()
    rows = []
    for draft in listing.get("drafts", []):
        message = _get_message(api, draft["message"]["id"], fmt="metadata")
        summary = gmailmsg.summarise(message)
        rows.append({"draft_id": draft["id"], **summary})

    def render(payload):
        table = [[d["draft_id"], output.truncate(d["to"], 30),
                  output.truncate(d["subject"], 50)] for d in payload["drafts"]]
        return output.table(table, headers=["DRAFT ID", "TO", "SUBJECT"]) or ["No drafts."]

    output.emit({"drafts": rows}, render)


def cmd_send(args):
    """Send a draft, or compose-and-send. Always requires --confirm."""
    api = _api(args)

    if args.draft_id:
        try:
            draft = api.users().drafts().get(userId=ME, id=args.draft_id, format="full").execute()
        except HttpError as exc:
            raise services.translate(exc) from exc
        detail = gmailmsg.detail(draft.get("message", {}))
        preview = {
            "to": [detail["to"]], "cc": [detail["cc"]] if detail["cc"] else [], "bcc": [],
            "subject": detail["subject"], "body": detail["body"],
            "attachments": [a["filename"] for a in detail["attachments"]],
            "thread_id": detail["thread_id"],
        }
        if not args.confirm:
            raise ConfirmationRequired(
                "Refusing to send without --confirm.\n"
                + "\n".join(_render_preview(preview))
                + f"\n\nTo send:  pa mail send --draft-id {args.draft_id} --confirm"
            )
        try:
            sent = api.users().drafts().send(userId=ME, body={"id": args.draft_id}).execute()
        except HttpError as exc:
            raise services.translate(exc) from exc
    else:
        body, preview = _build_mime(args, api)
        if not args.confirm:
            raise ConfirmationRequired(
                "Refusing to send without --confirm.\n"
                + "\n".join(_render_preview(preview))
                + "\n\nRe-run the same command with --confirm to send, or use "
                  "`pa mail draft ...` to save it for review first."
            )
        try:
            sent = api.users().messages().send(userId=ME, body=body).execute()
        except HttpError as exc:
            raise services.translate(exc) from exc

    def render(payload):
        return ["Sent.", f"  message id: {payload['id']}",
                f"  thread id:  {payload['thread_id']}"]

    output.emit({"id": sent.get("id"), "thread_id": sent.get("threadId"),
                 "preview": preview, "sent": True}, render)


def cmd_discard(args):
    """Delete a draft. Unlike a sent message this is genuinely unrecoverable,
    so it is confirmation-gated too."""
    api = _api(args)
    if not args.confirm:
        raise ConfirmationRequired(
            f"Refusing to discard draft {args.id} without --confirm "
            "(discarding a draft cannot be undone)."
        )
    try:
        api.users().drafts().delete(userId=ME, id=args.id).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    output.emit({"draft_id": args.id, "discarded": True},
                lambda p: [f"Discarded draft {p['draft_id']}."])


def cmd_label(args):
    api = _api(args)
    add, remove = args.add or [], args.remove or []
    if not add and not remove:
        raise UsageError("Nothing to do: pass --add and/or --remove")
    try:
        result = api.users().messages().modify(
            userId=ME, id=args.id,
            body={"addLabelIds": add, "removeLabelIds": remove},
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    output.emit({"id": result.get("id"), "labels": result.get("labelIds", [])},
                lambda p: [f"Labels now: {', '.join(p['labels'])}"])


def cmd_archive(args):
    api = _api(args)
    try:
        result = api.users().messages().modify(
            userId=ME, id=args.id, body={"removeLabelIds": ["INBOX"]}
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    output.emit({"id": result.get("id"), "labels": result.get("labelIds", []), "archived": True},
                lambda p: [f"Archived {p['id']}."])


def cmd_trash(args):
    """Move to Trash. Never a permanent delete — gmail.modify cannot do that."""
    api = _api(args)
    if not args.confirm:
        raise ConfirmationRequired(
            f"Refusing to trash message {args.id} without --confirm."
        )
    try:
        result = api.users().messages().trash(userId=ME, id=args.id).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    output.emit({"id": result.get("id"), "trashed": True},
                lambda p: [f"Moved {p['id']} to Trash (recoverable for 30 days)."])


def cmd_profile(args):
    api = _api(args)
    profile = api.users().getProfile(userId=ME).execute()
    output.emit(profile, lambda p: [
        f"Address:  {p.get('emailAddress')}",
        f"Messages: {p.get('messagesTotal')}",
        f"Threads:  {p.get('threadsTotal')}",
    ])


# ------------------------------------------------------------------ wiring


def _add_compose_flags(parser, *, allow_reply: bool = True):
    parser.add_argument("--to", action="append", help="Recipient (repeatable or comma-separated)")
    parser.add_argument("--cc", action="append", default=[])
    parser.add_argument("--bcc", action="append", default=[])
    parser.add_argument("--subject", default=None)
    parser.add_argument("--body", default=None, help="Message text")
    parser.add_argument("--body-file", default=None,
                        help="Read body from a file, or '-' for stdin")
    parser.add_argument("--attach", action="append", help="File to attach (repeatable)")
    if allow_reply:
        parser.add_argument("--reply-to-id", default=None,
                            help="Message id to reply to (sets threading headers)")


def register(subparsers, common):
    mail = subparsers.add_parser("mail", help="Gmail: search, read, draft, send, label")
    actions = mail.add_subparsers(dest="mail_command", required=True)

    p = actions.add_parser("search", parents=[common], help="Search messages with Gmail query syntax")
    p.add_argument("query", nargs="?", default="in:inbox",
                   help="Gmail query, e.g. 'from:alex is:unread newer_than:7d'")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.add_argument("--label", action="append", help="Restrict to label id (repeatable)")
    p.set_defaults(func=cmd_search)

    p = actions.add_parser("read", parents=[common], help="Read one message in full")
    p.add_argument("id")
    p.add_argument("--mark-read", action="store_true", help="Also remove the UNREAD label")
    p.set_defaults(func=cmd_read)

    p = actions.add_parser("thread", parents=[common], help="Read a whole conversation")
    p.add_argument("id")
    p.add_argument("--full", action="store_true", help="Do not truncate message bodies")
    p.set_defaults(func=cmd_thread)

    p = actions.add_parser("draft", parents=[common], help="Create a draft (safe; sends nothing)")
    _add_compose_flags(p)
    p.set_defaults(func=cmd_draft)

    p = actions.add_parser("drafts", parents=[common], help="List existing drafts")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(func=cmd_drafts)

    p = actions.add_parser("send", parents=[common], help="Send a draft or a new message (requires --confirm)")
    p.add_argument("--draft-id", default=None, help="Send an existing draft")
    _add_compose_flags(p)
    p.add_argument("--confirm", action="store_true",
                   help="Required. Without it the message is previewed, not sent.")
    p.set_defaults(func=cmd_send)

    p = actions.add_parser("discard", parents=[common], help="Delete a draft (requires --confirm)")
    p.add_argument("id")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_discard)

    p = actions.add_parser("labels", parents=[common], help="List all labels and their ids")
    p.set_defaults(func=cmd_labels)

    p = actions.add_parser("label", parents=[common], help="Add or remove labels on a message")
    p.add_argument("id")
    p.add_argument("--add", action="append")
    p.add_argument("--remove", action="append")
    p.set_defaults(func=cmd_label)

    p = actions.add_parser("archive", parents=[common], help="Remove a message from the inbox")
    p.add_argument("id")
    p.set_defaults(func=cmd_archive)

    p = actions.add_parser("trash", parents=[common], help="Move a message to Trash (requires --confirm)")
    p.add_argument("id")
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_trash)

    p = actions.add_parser("attachments", parents=[common], help="List or download attachments")
    p.add_argument("id")
    p.add_argument("--download", metavar="DIR", help="Directory to save attachments into")
    p.set_defaults(func=cmd_attachments)

    p = actions.add_parser("export", parents=[common],
                           help="Save a message's full RFC-822 original as a .eml file")
    p.add_argument("id")
    p.add_argument("--out", metavar="PATH",
                   help="Output file, or a directory (writes <id>.eml). "
                        "Defaults to <id>.eml in the current directory.")
    p.set_defaults(func=cmd_export)

    p = actions.add_parser("profile", parents=[common], help="Show the authenticated mailbox")
    p.set_defaults(func=cmd_profile)
