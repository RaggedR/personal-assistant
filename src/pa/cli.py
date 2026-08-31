"""Argument parsing and the top-level entry point.

Design notes:

* Every subcommand is a plain function taking the parsed ``args`` namespace and
  printing through ``output.emit``. There is no framework, so behaviour is easy
  to read and to unit test.
* Errors surface as a one-line ``pa: ...`` message on stderr plus a meaningful
  exit code (see ``pa.errors``), never a traceback — a traceback is useless to
  an agent and alarming to a human.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, config, output
from .commands import auth_cmd, cal, contacts, mail
from .errors import PaError

EPILOG = """\
examples:
  pa auth status
  pa mail search 'from:alex is:unread' -n 10
  pa mail read 18f2c3a4b5 --mark-read
  pa mail draft --to alex@example.com --subject 'Grant draft' --body 'See attached.'
  pa mail send --draft-id r-8837 --confirm
  pa cal list --from today --to +7d
  pa cal create --title 'Kodamai sync' --start 'tomorrow 10:00' --duration 45
  pa contacts resolve 'alex'

Sending mail and deleting events require --confirm; without it you get a
preview and a non-zero exit. Add --json to any command for machine output.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa",
        description="Personal assistant CLI for Gmail, Google Calendar and Contacts.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"pa {__version__}")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--account", default=None,
                        help="Account nickname (default: $PA_ACCOUNT or 'default')")

    # The same flags are accepted before OR after the subcommand, because
    # `pa mail search x --json` is what people actually type. SUPPRESS is
    # essential: without it the leaf parser's default would clobber a value
    # already set at the top level, since the leaf parses second.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)
    common.add_argument("--account", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in (auth_cmd, mail, cal, contacts):
        module.register(subparsers, common)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output.set_json(getattr(args, "json", False))

    account = getattr(args, "account", None)
    if account:
        import os

        os.environ["PA_ACCOUNT"] = account

    try:
        args.func(args)
    except PaError as exc:
        if output.json_mode():
            import json

            json.dump({"error": type(exc).__name__, "message": str(exc)},
                      sys.stderr, indent=2)
            sys.stderr.write("\n")
        else:
            print(f"pa: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Downstream `head`/`less` closed the pipe; that is not an error.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
