# `wa` — WhatsApp from the command line

`wa` ships in this repository alongside `pa`, but it is **optional and
structurally different**, so it has its own page.

## Why it is different

Gmail and Calendar have official HTTP APIs, so `pa` is stateless: every command
authenticates, does its work, and exits. WhatsApp has no such API. `wa` sits on
top of [`lharries/whatsapp-mcp`](https://github.com/lharries/whatsapp-mcp),
whose Go bridge speaks the WhatsApp Web protocol via
[`whatsmeow`](https://github.com/tulir/whatsmeow) and must hold a live session.

That has two consequences you cannot design away:

1. **Reads come from a database, not from WhatsApp.** The bridge records
   incoming messages into SQLite as they arrive. If the bridge is not running,
   messages are never recorded — and a later read shows a gap, silently. `wa`
   was written after exactly that happened: the bridge had been down for 51
   days while the MCP server still reported itself "connected".
2. **Sending requires the bridge to be up.** There is nothing to queue against.

Hence `wa status`, which reports both facts and warns when the store is stale.
Run it first, always.

```console
$ wa status
Bridge:   NOT RUNNING  (http://localhost:8080/api)
Store:    /Users/robin/git/whatsapp-mcp/whatsapp-bridge/store/messages.db
Chats:    108
Messages: 3179
Newest:   Sat 11 Jul 10:50

  Warning: the newest message is 51 days old. Incoming messages are
  only recorded while the bridge runs, so reads are stale until you
  start it:  wa bridge start

  Sending is unavailable until the bridge is running.
```

## Setup

```bash
git clone https://github.com/lharries/whatsapp-mcp.git ~/git/whatsapp-mcp
cd ~/git/whatsapp-mcp/whatsapp-bridge && go build     # needs Go
wa bridge start --foreground                          # scan the QR with your phone
```

The first run prints a QR code to be scanned from **WhatsApp → Settings →
Linked devices**, so it needs a real terminal — hence `--foreground`. The
session persists afterwards, and `wa bridge start` can run it detached.

Override the location with `WA_BRIDGE_DIR`, the database with `WA_MESSAGES_DB`,
or the endpoint with `WA_API_BASE`.

## Safety

Sending is confirmation-gated exactly as in `pa`, and for a stronger reason:
WhatsApp has no draft folder and no unsend. Without `--confirm` you get a
preview naming both the resolved contact **and** the exact JID, and exit code 7.

```console
$ wa send --to 'Project Team' --message 'test message'
wa: Refusing to send without --confirm.
────────────────────────────────────────────────────────────
To:   Project Team (group)
JID:  120363000000000000@g.us
────────────────────────────────────────────────────────────
test message
────────────────────────────────────────────────────────────

Re-run with --confirm to send. Check the recipient above carefully —
WhatsApp messages cannot be unsent to a wrong number.
```

Recipient resolution is deliberately pedantic, because misdelivery is the
failure that matters:

- A name fragment matching more than one chat is **refused**, with the
  candidates listed. It never picks one.
- A local-format number (`0412345678`) is **refused** rather than having a
  country code guessed onto it. WhatsApp wants `61412345678`.
- A number shorter than eight digits is refused.

## Commands

| Command | Purpose |
|---|---|
| `status` | Bridge up? Store fresh? **Run this first.** |
| `chats` | Chats, most recent first; `--groups`, `-q` to filter |
| `read CHAT` | A conversation, oldest-first; accepts JID, number or name |
| `search QUERY` | Search message text; `--chat` to narrow |
| `context ID` | Messages either side of one message |
| `contacts QUERY` | Search contacts, including group members |
| `resolve QUERY` | Print one JID for a name — for scripting |
| `send` | Send text and/or a file — **requires `--confirm`** |
| `download ID` | Fetch a message's media |
| `bridge status\|start\|stop\|logs` | Manage the bridge process |

## Known data limitations

These are properties of the bridge's recorded data, not of `wa`:

- **Group senders are often missing.** For many group messages the bridge wrote
  the *group's own* id into the `sender` column instead of the member who spoke.
  `wa` renders those as `(unknown)` rather than inventing a participant. In
  one-to-one chats senders are correct.
- **Contact names are frequently blank**, so chats show a phone number. WhatsApp
  only supplies a name when the sender has a public "pushname".
- **History starts when the bridge first ran.** It cannot backfill.

For deep history, Robin's separate ChromaDB export covers ~79k messages:

```bash
python ~/git/news/whatsapp_vectordb.py query "..."
```

That is semantic search over an export; `wa` is live structured access. They
complement each other.

## Timestamps

The bridge stores timestamps as text with a UTC offset
(`2026-07-11 10:50:17+10:00`). Sorting that text lexicographically is *almost*
right and wrong exactly at a daylight-saving change: `02:00+10:00` sorts before
`02:30+11:00` as a string but is the later instant. Every comparison in `wa`
therefore goes through `strftime('%s', timestamp)`. `tests/test_wa_timestamps.py`
pins this, including a test asserting the naive version really is wrong.
