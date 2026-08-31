# CLAUDE.md — personal-assistant (`pa`)

Guidance for Claude Code working *on this repository*. For using the tool, see
[README.md](README.md).

## What this is

A CLI giving agents and humans access to Gmail, Google Calendar and Google
Contacts. It exists to replace the `@gongrzhe` Gmail/Calendar MCP servers, whose
~25 tool schemas were loaded into every conversation's context whether used or
not. A CLI costs nothing until invoked.

Public repo, shared with Neil Ghani and Marie-Claire. **Never commit a
credential.** `.gitignore` covers `client.json`, `token.json`,
`credentials.json`, `gcp-oauth.keys.json`, `client_secret*.json`, `.env`.

## Layout

```
src/pa/
  cli.py          argparse tree, error→exit-code mapping, entry point
  auth.py         scope table, credential resolution, OAuth login
  config.py       filesystem layout, account resolution, atomic JSON writes
  services.py     API client construction, HttpError → typed error
  gmailmsg.py     MIME payload decoding (pure, no network — heavily tested)
  timeparse.py    lenient date/time parsing (pure, heavily tested)
  output.py       text/JSON rendering; the only place that prints
  errors.py       typed errors carrying exit codes
  commands/       one module per group: mail, cal, contacts, auth_cmd
src/wa/           the `wa` WhatsApp CLI (optional; see docs/WHATSAPP.md)
  jid.py          JID parsing and recipient normalisation (pure, tested)
  store.py        read-only SQLite queries against the bridge's store
  bridge.py       HTTP client for the Go bridge + process control
  cli.py          argparse tree and commands
tests/            fully offline
docs/SETUP.md     the OAuth onboarding walkthrough
docs/WHATSAPP.md  why `wa` needs a daemon, and its data limitations
ONBOARDING.md     setup script addressed to Claude, for new users
```

`wa` reuses `pa.output`, `pa.errors` and `pa.timeparse` rather than duplicating
them. That is deliberate: they are generic, and two frontends over shared
primitives is simpler than a third package. Do not fork them.

## Invariants — do not break these

1. **Confirmation gates.** `mail send`, `mail trash`, `mail discard` and
   `cal delete` must raise `ConfirmationRequired` (exit 7) unless `--confirm`
   was passed, and must make **no** mutating API call in that case.
   `tests/test_send_guard.py` asserts the API was never touched, not merely that
   an exception was raised. If you add an outbound or destructive command, gate
   it the same way and add the same style of test.
2. **Never request `https://mail.google.com/`.** `gmail.modify` is deliberate:
   it cannot permanently delete mail. Trash-only is a feature.
3. **Never write to `~/.gmail-mcp` or `~/.calendar-mcp`.** They are a read-only
   compatibility fallback. `auth.credentials_for` sets `persist_to = None` for
   that path on purpose.
4. **Legacy fallback is default-account only.** A named account must never
   silently borrow the default's credentials.
5. **All printing goes through `output.emit`.** A bare `print` in a command
   corrupts `--json` output. Human-only commentary uses `output.note`, which is
   suppressed in JSON mode.
6. **Naive datetimes are localised, never assumed UTC.** `timeparse.localise`.
   The Melbourne offset test guards the classic ten-hour bug.
7. **Errors are typed.** Raise from `pa.errors` so the exit code is right;
   `cli.main` prints one line, never a traceback.
8. **Tests stay offline.** `tests/conftest.py` redirects both `PA_HOME` and
   `config.LEGACY_MCP_DIRS` into a temp dir; `wa` tests point `WA_MESSAGES_DB`
   at a temp SQLite file. Never add a test that needs network or the
   developer's own credentials.

### `wa`-specific invariants

9. **Never compare bridge timestamps as strings.** They are text with a UTC
    offset, so `02:00+10:00` sorts before `02:30+11:00` while being the *later*
    instant. Every filter and every `ORDER BY` must go through
    `strftime('%s', timestamp)`. This bug was introduced and fixed three times
    during development — in range filters, in `ORDER BY`, and in `stats()`'s
    `MAX()`. `tests/test_wa_timestamps.py` pins all three and includes a test
    asserting the naive version really is wrong.
10. **The store is opened read-only** (`mode=ro`). The bridge is the sole
    writer; `wa` must never be able to lock or corrupt it.
11. **Never guess a recipient.** An ambiguous name is refused with candidates
    listed; a local-format number is refused rather than having a country code
    added. Misdelivery is unrecoverable — there is no unsend.
12. **Do not invent group senders.** The bridge often records a group's own id
    in `sender`. Render that as `(unknown)`. The heuristic applies to groups
    only: in a one-to-one chat, sender equalling the chat id is normal.

## Adding a subcommand

In the relevant `commands/*.py`:

```python
def cmd_thing(args):
    api = _api(args)
    ...
    output.emit(payload, render)      # render returns lines, or a string

# in register(subparsers, common):
p = actions.add_parser("thing", parents=[common], help="...")
p.add_argument("id")
p.set_defaults(func=cmd_thing)
```

`parents=[common]` is required — it is what makes `--json` and `--account` work
*after* the subcommand, which is how people actually type them. The common flags
use `argparse.SUPPRESS` as their default so the leaf parser cannot clobber a
value already set at the top level.

Wrap every Google call in `try/except HttpError` and
`raise services.translate(exc) from exc`.

## Testing

```bash
python3 -m pytest -q            # 125 tests, ~0.7s, no network
```

Pure modules (`gmailmsg`, `timeparse`, `output`, `auth._covers`) are where the
real logic lives and should carry the bulk of the coverage. Command functions
are tested against the fake Gmail API in `tests/test_send_guard.py` — extend
that fake rather than reaching for the network.

## Local install

`pipx` is broken on Robin's machine (Homebrew Python 3.14 has a mismatched
`libexpat`). Use `uv`:

```bash
~/pygame_env/bin/uv tool install --editable .
```

## Conventions

Australian/British spelling in user-facing prose ("authorise", "organisation").
Comments explain *why*, never *what*. Docstrings on modules and non-obvious
functions; none on self-evident ones.
