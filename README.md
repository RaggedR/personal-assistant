# pa — a personal assistant CLI

Command-line access to **Gmail**, **Google Calendar** and **Google Contacts**,
designed to be driven either by a human at a terminal or by an AI coding agent
such as [Claude Code](https://claude.com/claude-code).

```console
$ pa cal list --from today --to +3d
DAY               TIME   EVENT                     WHERE  ID
----------------  -----  ------------------------  -----  --------------------------
Mon 31 Aug 09:00  09:00  Standup                   Zoom   98oqokrpkb3j02k7rin70rsd8c
                  16:30  Design review                    9agl00v4h238lnnd044mjrrdb8
Tue 01 Sep 18:00  18:00  Reading group                    3lbqtsiut93j4elt3r370tn5q8

$ pa mail search 'from:alex is:unread' -n 3
$ pa mail draft --to alex@example.com --subject 'Grant draft' --body 'Notes attached.'
$ pa mail send --draft-id r8511839562792451920 --confirm
```

## Why a CLI and not an MCP server?

Both are valid ways to give an agent these capabilities. This project
deliberately chooses a CLI:

| | MCP server | CLI |
|---|---|---|
| **Context cost** | Every tool schema is loaded into the model's context on *every* session, whether or not it is used | Zero until invoked; the agent reads `pa --help` on demand |
| **Human usability** | Only reachable through an agent | Usable directly, scriptable, cron-able, pipeable into `jq` |
| **Testability** | Needs an MCP client to exercise | Plain subprocess with an exit code |
| **Composability** | Bespoke protocol | `pa ... --json \| jq`, shell pipelines, Makefiles |
| **Auditability** | Calls happen inside a protocol stream | Every call is a shell command in your history |

A Gmail + Calendar MCP pair costs roughly 25 tool schemas of context in every
conversation. `pa` costs nothing until it is called.

## Safety model

Outbound and destructive actions are **refused unless explicitly confirmed**.
This is enforced in the tool, not merely documented, so an over-eager agent
cannot send mail on your behalf by accident.

```console
$ pa mail send --to alex@example.com --subject 'Hi' --body 'Hello'
pa: Refusing to send without --confirm.
────────────────────────────────────────────────────────────
To:      alex@example.com
Subject: Hi
────────────────────────────────────────────────────────────
Hello
────────────────────────────────────────────────────────────

Re-run the same command with --confirm to send, or use
`pa mail draft ...` to save it for review first.

$ echo $?
7
```

Confirmation is required for: `mail send`, `mail trash`, `mail discard`,
`cal delete`. Everything else is either read-only or trivially reversible.
The intended workflow for an agent is **draft → human reviews → send**:

```console
$ pa mail draft --to alex@example.com --subject 'Grant' --body-file notes.txt
$ pa mail send --draft-id <id> --confirm
```

Permanent deletion is not implemented at all. `pa mail trash` moves a message
to Trash, where Gmail keeps it for 30 days.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/RaggedR/personal-assistant.git
cd personal-assistant

# with uv (recommended)
uv tool install --editable .

# or with pipx
pipx install --editable .

# or into a plain virtualenv
python3 -m venv .venv && .venv/bin/pip install -e .
```

Then authorise your Google account — a one-time setup documented step by step
in **[docs/SETUP.md](docs/SETUP.md)**:

```bash
pa auth setup-client ~/Downloads/client_secret_XXXX.json
pa auth login
pa auth status
```

## Commands

Run `pa <group> --help` for full flags. Add `--json` to any command for
machine-readable output; add it before or after the subcommand, whichever you
prefer.

### `pa mail`

| Command | Purpose |
|---|---|
| `search [QUERY]` | Search with [Gmail query syntax](https://support.google.com/mail/answer/7190) (default `in:inbox`) |
| `read ID` | Full message: headers, decoded body, attachment list |
| `thread ID` | Whole conversation, bodies truncated unless `--full` |
| `draft` | Create a draft — never sends |
| `drafts` | List existing drafts with their ids |
| `send` | Send a draft or a new message — **requires `--confirm`** |
| `discard ID` | Delete a draft — **requires `--confirm`** |
| `labels` | List labels and their ids |
| `label ID` | `--add` / `--remove` labels |
| `archive ID` | Remove from the inbox |
| `trash ID` | Move to Trash — **requires `--confirm`** |
| `attachments ID` | List, or `--download DIR` to save |
| `profile` | Which mailbox am I authenticated as? |

Compose flags (`draft` and `send`): `--to`, `--cc`, `--bcc` (repeatable or
comma-separated), `--subject`, `--body`, `--body-file` (`-` for stdin),
`--attach` (repeatable), `--reply-to-id` (sets `In-Reply-To`/`References` and
threads correctly, honouring the original's `Reply-To`).

### `pa cal`

| Command | Purpose |
|---|---|
| `list` | Agenda for a range, grouped by day |
| `show ID` | One event in full, including attendee responses |
| `create` | New event; `--duration MINUTES` as an `--end` alternative |
| `update ID` | Patch any subset of fields |
| `delete ID` | Delete — **requires `--confirm`** |
| `rsvp ID` | `--response accepted\|declined\|tentative\|needsAction` |
| `freebusy` | Busy blocks across one or more calendars |
| `calendars` | List calendars you can see |

Recurring series are expanded into individual instances, so `list` shows what
is actually on. Attendees are only emailed when you pass `--notify`.

### `pa contacts`

| Command | Purpose |
|---|---|
| `search QUERY` | Search saved contacts *and* "other contacts" |
| `resolve QUERY` | Print the single best email address — exits 4 if none |
| `list` | List saved contacts |

`resolve` exists for scripting: `pa mail draft --to "$(pa contacts resolve alex)" ...`

### `pa auth`

| Command | Purpose |
|---|---|
| `setup-client PATH` | Install a downloaded Google OAuth client JSON |
| `login` | Browser OAuth flow; `--force` to re-consent, `--service` to narrow |
| `status` | Where credentials come from, and a live check that each works |
| `accounts` | List configured accounts |
| `logout` | Delete a stored token |

## Dates and times

Anywhere a time is accepted:

```
now                          today / tomorrow / yesterday
mon … sun                    next occurrence of that weekday
+3d  -2h  +90m  +1w          offsets from now
2026-09-01                   a date (midnight, local)
2026-09-01 14:00             local time
2026-09-01T14:00:00+10:00    full ISO 8601, honoured as given
1 Sep 2026 2pm               anything dateutil understands
```

Naive times are interpreted in your local zone, never UTC. Day-only range
bounds expand to cover the whole day, so `--from today --to today` means all of
today rather than a zero-width window.

## Multiple accounts

```bash
pa --account kodamai auth login       # authorise a second account
pa --account kodamai mail search      # use it
export PA_ACCOUNT=kodamai             # or make it the default for a shell
```

Credentials live in `~/.config/pa/accounts/<name>/token.json`, mode `0600`.
Override the root with `PA_HOME`.

## Exit codes

Meaningful exit codes let callers branch without parsing prose.

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unspecified error |
| 2 | Bad arguments |
| 3 | Not authenticated, or missing a required scope |
| 4 | Message, thread, event or contact not found |
| 5 | Google API error |
| 7 | Confirmation required — nothing was sent or deleted |

## For AI agents

`pa` is built to be agent-legible:

- `--json` on everything, with stable key names.
- Human commentary goes to stdout only in text mode, so JSON output is always
  parseable; errors go to stderr as JSON when `--json` is set.
- Ids are printed in every listing, so a listing can be piped into a `read`.
- Confirmation gates mean an agent can attempt an action, receive a preview and
  exit code 7, and surface that preview to its human for approval.

Suggested instruction to put in your agent's configuration:

> Use the `pa` CLI for all email and calendar access. Never pass `--confirm`
> to `pa mail send` without explicit, per-message permission from me in the
> current conversation. Drafting is always fine.

## Migrating from the Gmail/Calendar MCP servers

If you already use `@gongrzhe/server-gmail-autoauth-mcp` or
`@gongrzhe/server-calendar-autoauth-mcp`, `pa` reads their credential
directories (`~/.gmail-mcp`, `~/.calendar-mcp`) as a read-only fallback, so
mail and calendar work with **no setup at all**. It never writes to them.

`pa auth status` shows the provenance of each service:

```console
$ pa auth status
  [ok  ] gmail     legacy MCP (/Users/you/.gmail-mcp)  you@gmail.com
  [ok  ] calendar  legacy MCP (/Users/you/.calendar-mcp)
  [none] contacts  none
```

Run `pa auth login` when you want to consolidate onto `pa`'s own store and add
Contacts, then remove the MCP servers from your agent's configuration.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

The test suite is fully offline: `PA_HOME` and the legacy MCP directories are
both redirected into a temp dir, and the Gmail API is faked, so tests neither
touch the network nor depend on the developer's own credentials.

## Licence

MIT — see [LICENSE](LICENSE).
