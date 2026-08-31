"""wa — WhatsApp from the command line.

Reads come straight from the bridge's SQLite store; sends go through the running
bridge. Outbound actions are confirmation-gated exactly as in ``pa``: a WhatsApp
message is as unrecoverable as an email, arguably more so, since there is no
draft folder to stage it in.
"""

from __future__ import annotations

import argparse
import sys

from pa import output
from pa import timeparse
from pa.errors import ConfirmationRequired, PaError, UsageError

from . import __version__, bridge, config, jid as jidmod, store

EPILOG = """\
examples:
  wa status
  wa chats -n 15
  wa read 'Alex Example' -n 30
  wa search 'grant' --chat 61412345678
  wa contacts alex
  wa send --to 61412345678 --message 'On my way' --confirm
  wa bridge start

Sending requires --confirm; without it you get a preview showing exactly who
would receive it, and a non-zero exit. Add --json to any command.
"""


def _stamp(value: str | None) -> str:
    parsed = store.parse_timestamp(value)
    return timeparse.humanise(parsed.isoformat()) if parsed else "?"


# --------------------------------------------------------------------- status


def cmd_status(args):
    running = bridge.is_running()
    info = {"bridge_running": running, "api": config.api_base(),
            "bridge_dir": str(config.bridge_dir())}
    try:
        info.update(store.stats())
        info["store_available"] = True
    except store.StoreUnavailable as exc:
        info["store_available"] = False
        info["store_error"] = str(exc)

    def render(p):
        lines = [
            f"Bridge:   {'running' if p['bridge_running'] else 'NOT RUNNING'}  ({p['api']})",
            f"Store:    {p.get('database', p['bridge_dir'])}",
        ]
        if not p["store_available"]:
            lines.append("          unavailable — the bridge has never run")
            return lines
        lines += [
            f"Chats:    {p['chats']}",
            f"Messages: {p['messages']}",
            f"Newest:   {_stamp(p['latest'])}",
        ]
        stale = p.get("stale_days")
        if stale is not None and stale > 1:
            lines.append("")
            lines.append(
                f"  Warning: the newest message is {stale} days old. Incoming "
                "messages are\n  only recorded while the bridge runs, so reads are "
                "stale until you\n  start it:  wa bridge start"
            )
        if not p["bridge_running"]:
            lines.append("")
            lines.append("  Sending is unavailable until the bridge is running.")
        return lines

    output.emit(info, render)


# ----------------------------------------------------------------- read side


def cmd_chats(args):
    found = store.chats(limit=args.limit, query=args.query,
                        groups_only=args.groups)

    def render(p):
        if not p["chats"]:
            return ["No chats matched."]
        rows = []
        for chat in p["chats"]:
            preview = chat.get("last_message", "") or ""
            if chat.get("last_is_from_me"):
                preview = f"→ {preview}"
            rows.append([_stamp(chat["last_message_time"]),
                         "grp" if chat["is_group"] else "   ",
                         output.truncate(chat["label"], 26),
                         output.truncate(preview, 44),
                         chat["jid"]])
        return output.table(rows, headers=["WHEN", "", "WHO", "LAST MESSAGE", "JID"])

    output.emit({"count": len(found), "chats": found}, render)


def cmd_read(args):
    chat = store.resolve_chat(args.chat)
    after, before = None, None
    if args.start or args.end:
        after, before = timeparse.parse_range(args.start, args.end, default_days=3650)
    found = store.messages(chat["jid"], limit=args.limit, after=after,
                           before=before, media_only=args.media)

    def render(p):
        lines = [f"{p['chat']['label']}   {p['chat']['jid']}",
                 f"{len(p['messages'])} message(s)", ""]
        if not p["messages"]:
            return lines + ["(nothing in range)"]
        for message in p["messages"]:
            who = "me" if message["from_me"] else (
                p["chat"]["label"] if not p["chat"]["is_group"]
                else message["sender_label"])
            body = message["content"] or f"[{message['media_type'] or 'no text'}]"
            if message["media_type"]:
                body = f"[{message['media_type']}{': ' + message['filename'] if message['filename'] else ''}] {body}".strip()
            lines.append(f"{_stamp(message['timestamp'])}  {who:>14}: {body}")
        return lines

    output.emit({"chat": chat, "messages": found}, render)


def cmd_search(args):
    chat_jid = store.resolve_chat(args.chat)["jid"] if args.chat else None
    found = store.messages(chat_jid, limit=args.limit, query=args.query)

    def render(p):
        if not p["messages"]:
            return [f"No messages containing {p['query']!r}."]
        rows = [[_stamp(m["timestamp"]),
                 output.truncate(m["chat_name"] or jidmod.describe(m["chat_jid"]), 20),
                 "me" if m["from_me"] else output.truncate(m["sender_label"], 14),
                 output.truncate(m["content"], 50),
                 m["id"]] for m in p["messages"]]
        return output.table(rows, headers=["WHEN", "CHAT", "FROM", "MESSAGE", "ID"])

    output.emit({"query": args.query, "count": len(found), "messages": found}, render)


def cmd_context(args):
    found = store.context(args.id, before=args.before, after=args.after)

    def render(p):
        lines = [f"{p['chat_name'] or p['chat_jid']}", ""]
        for message in p["before"]:
            lines.append(f"     {_stamp(message['timestamp'])}  "
                         f"{'me' if message['from_me'] else message['sender_label']}: "
                         f"{message['content']}")
        target = p["target"]
        lines.append(f"  >> {_stamp(target['timestamp'])}  "
                     f"{'me' if target['from_me'] else target['sender_label']}: "
                     f"{target['content']}")
        for message in p["after"]:
            lines.append(f"     {_stamp(message['timestamp'])}  "
                         f"{'me' if message['from_me'] else message['sender_label']}: "
                         f"{message['content']}")
        return lines

    output.emit(found, render)


def cmd_contacts(args):
    found = store.contacts(args.query, limit=args.limit)

    def render(p):
        if not p["contacts"]:
            return [f"No contacts matching {p['query']!r}."]
        rows = [[c["source"], output.truncate(c["label"], 28), c["jid"],
                 _stamp(c["last_seen"])] for c in p["contacts"]]
        return output.table(rows, headers=["SOURCE", "WHO", "JID", "LAST SEEN"])

    output.emit({"query": args.query, "contacts": found}, render)


def cmd_resolve(args):
    """Print one JID for a name — the scripting counterpart to `pa contacts resolve`."""
    chat = store.resolve_chat(args.query)
    output.emit({"query": args.query, "jid": chat["jid"], "label": chat["label"]},
                lambda p: [p["jid"]])


# ---------------------------------------------------------------- write side


def _preview(recipient_label: str, recipient_jid: str, message: str,
             media: str | None) -> list[str]:
    lines = ["─" * 60, f"To:   {recipient_label}", f"JID:  {recipient_jid}"]
    if media:
        lines.append(f"File: {media}")
    lines += ["─" * 60, message or "(no text)", "─" * 60]
    return lines


def _resolve_recipient(value: str) -> tuple[str, str]:
    """Return (jid, label). Falls back to a raw JID when there is no chat yet."""
    try:
        chat = store.resolve_chat(value)
        return chat["jid"], chat["label"]
    except (store.StoreUnavailable, PaError):
        # No local chat history — a bare number is still a valid recipient.
        target = jidmod.normalise(value)
        return target, jidmod.describe(target)


def cmd_send(args):
    if not args.message and not args.file:
        raise UsageError("Provide --message and/or --file")
    recipient, label = _resolve_recipient(args.to)
    message = args.message or ""

    if not args.confirm:
        raise ConfirmationRequired(
            "Refusing to send without --confirm.\n"
            + "\n".join(_preview(label, recipient, message, args.file))
            + "\n\nRe-run with --confirm to send. Check the recipient above "
              "carefully — WhatsApp messages cannot be unsent to a wrong number."
        )

    result = bridge.send(recipient, message, args.file)

    def render(p):
        return [f"Sent to {p['label']} ({p['jid']}).",
                f"  {p['result'].get('message', 'ok')}"]

    output.emit({"jid": recipient, "label": label, "message": message,
                 "file": args.file, "sent": True, "result": result}, render)


def cmd_download(args):
    record = store.media_message(args.id)
    result = bridge.download(args.id, record["chat_jid"])
    output.emit({"id": args.id, "chat_jid": record["chat_jid"], **result},
                lambda p: [f"Downloaded to {p.get('path') or p.get('filename')}"])


# ------------------------------------------------------------------- bridge


def cmd_bridge(args):
    if args.bridge_command == "status":
        payload = {"running": bridge.is_running(), "port_open": bridge.port_open(),
                   "binary": str(config.bridge_binary()),
                   "binary_present": config.bridge_binary().exists(),
                   "log": str(bridge.LOG_PATH)}

        def render(p):
            lines = [f"Running: {'yes' if p['running'] else 'no'}",
                     f"Binary:  {p['binary']} "
                     f"({'present' if p['binary_present'] else 'MISSING — run: go build'})"]
            if p["port_open"] and not p["running"]:
                lines.append("Warning: something is listening on that port but it is "
                             "not the bridge.")
            return lines

        output.emit(payload, render)

    elif args.bridge_command == "start":
        result = bridge.start(foreground=args.foreground)
        if result.get("already_running"):
            output.emit(result, lambda p: ["Bridge is already running."])
            return
        if result.get("foreground"):
            output.emit(result, lambda p: ["Bridge exited."])
            return
        output.emit(result, lambda p: [
            f"Bridge started (pid {p['pid']}).",
            f"Logs: {p['log']}",
            "If this is the first run, it needs a QR code scanned from your phone —"
            " stop it and re-run with:  wa bridge start --foreground",
        ])

    elif args.bridge_command == "stop":
        output.emit(bridge.stop(), lambda p: [
            f"Stopped (pid {p['pid']})." if p["stopped"] else "Bridge was not running."])

    else:  # logs
        lines = bridge.tail_log(args.limit)
        output.emit({"log": str(bridge.LOG_PATH), "lines": lines},
                    lambda p: p["lines"] or ["(log is empty)"])


# ------------------------------------------------------------------- wiring


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wa", description="WhatsApp from the command line, via the local bridge.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"wa {__version__}")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)

    actions = parser.add_subparsers(dest="command", required=True)

    p = actions.add_parser("status", parents=[common],
                           help="Is the bridge up, and how fresh is the store?")
    p.set_defaults(func=cmd_status)

    p = actions.add_parser("chats", parents=[common], help="List chats, most recent first")
    p.add_argument("-n", "--limit", type=int, default=30)
    p.add_argument("-q", "--query", default=None, help="Filter by name or JID")
    p.add_argument("--groups", action="store_true", help="Groups only")
    p.set_defaults(func=cmd_chats)

    p = actions.add_parser("read", parents=[common], help="Read a conversation")
    p.add_argument("chat", help="JID, phone number, or a name fragment")
    p.add_argument("-n", "--limit", type=int, default=30)
    p.add_argument("--from", dest="start", default=None)
    p.add_argument("--to", dest="end", default=None)
    p.add_argument("--media", action="store_true", help="Only messages with media")
    p.set_defaults(func=cmd_read)

    p = actions.add_parser("search", parents=[common], help="Search message text")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=25)
    p.add_argument("--chat", default=None, help="Restrict to one chat")
    p.set_defaults(func=cmd_search)

    p = actions.add_parser("context", parents=[common],
                           help="Show messages around one message id")
    p.add_argument("id")
    p.add_argument("--before", type=int, default=5)
    p.add_argument("--after", type=int, default=5)
    p.set_defaults(func=cmd_context)

    p = actions.add_parser("contacts", parents=[common], help="Search contacts")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(func=cmd_contacts)

    p = actions.add_parser("resolve", parents=[common],
                           help="Print the single JID for a name")
    p.add_argument("query")
    p.set_defaults(func=cmd_resolve)

    p = actions.add_parser("send", parents=[common],
                           help="Send a message or file (requires --confirm)")
    p.add_argument("--to", required=True, help="JID, phone number, or name fragment")
    p.add_argument("--message", default=None)
    p.add_argument("--file", default=None, help="Path to a file to send")
    p.add_argument("--confirm", action="store_true",
                   help="Required. Without it the message is previewed, not sent.")
    p.set_defaults(func=cmd_send)

    p = actions.add_parser("download", parents=[common], help="Download a message's media")
    p.add_argument("id")
    p.set_defaults(func=cmd_download)

    p = actions.add_parser("bridge", parents=[common], help="Manage the bridge process")
    sub = p.add_subparsers(dest="bridge_command", required=True)
    q = sub.add_parser("status", parents=[common]); q.set_defaults(func=cmd_bridge)
    q = sub.add_parser("start", parents=[common])
    q.add_argument("--foreground", action="store_true",
                   help="Run attached, so a first-time QR code is visible")
    q.set_defaults(func=cmd_bridge)
    q = sub.add_parser("stop", parents=[common]); q.set_defaults(func=cmd_bridge)
    q = sub.add_parser("logs", parents=[common])
    q.add_argument("-n", "--limit", type=int, default=40)
    q.set_defaults(func=cmd_bridge)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output.set_json(getattr(args, "json", False))
    try:
        args.func(args)
    except PaError as exc:
        if output.json_mode():
            import json

            json.dump({"error": type(exc).__name__, "message": str(exc)},
                      sys.stderr, indent=2)
            sys.stderr.write("\n")
        else:
            print(f"wa: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
