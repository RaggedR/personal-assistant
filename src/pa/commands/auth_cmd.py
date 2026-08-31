"""Authentication subcommands: login, status, logout, accounts, setup-client."""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import auth, config, output
from ..errors import UsageError


def cmd_login(args):
    scopes = auth.ALL_SCOPES
    if args.service:
        scopes = sorted({s for svc in args.service for s in auth.SCOPES[svc]})
    account = config.resolve_account(args.account)

    if args.force:
        auth.logout(account)

    output.note(f"Opening a browser to authorise account '{account}'…")
    creds = auth.login(account, scopes)
    output.emit(
        {"account": account, "scopes": list(creds.scopes or []),
         "token": str(config.token_path(account))},
        lambda p: [f"Authorised '{p['account']}'.",
                   f"  token:  {p['token']}",
                   f"  scopes: {len(p['scopes'])} granted"],
    )


def cmd_status(args):
    account = config.resolve_account(args.account)
    services = {}
    for name in auth.SCOPES:
        services[name] = {"source": auth.describe_source(name, account), "ok": False,
                          "identity": None}
        if services[name]["source"] == "none":
            continue
        try:
            # A cheap authenticated call per service proves the token really works.
            if name == "gmail":
                from .. import services as svc

                profile = svc.service("gmail", account).users().getProfile(userId="me").execute()
                services[name]["identity"] = profile.get("emailAddress")
            elif name == "calendar":
                from .. import services as svc

                svc.service("calendar", account).calendarList().list(maxResults=1).execute()
            else:
                from .. import services as svc

                svc.service("contacts", account).people().connections().list(
                    resourceName="people/me", personFields="names", pageSize=1
                ).execute()
            services[name]["ok"] = True
        except Exception as exc:
            services[name]["error"] = str(exc)[:200]

    payload = {
        "account": account,
        "pa_home": str(config.pa_home()),
        "client": str(config.client_path(account)),
        "client_present": config.client_path(account).exists(),
        "accounts": config.list_accounts(),
        "timezone": config.default_timezone(),
        "services": services,
    }

    def render(p):
        lines = [f"Account:  {p['account']}",
                 f"Home:     {p['pa_home']}",
                 f"Timezone: {p['timezone']}",
                 f"Client:   {p['client']} "
                 f"({'present' if p['client_present'] else 'MISSING'})",
                 ""]
        for name, info in p["services"].items():
            mark = "ok  " if info["ok"] else ("fail" if info["source"] != "none" else "none")
            detail = info.get("identity") or info.get("error", "")
            lines.append(f"  [{mark}] {name:<9} {info['source']}"
                         + (f"  {detail}" if detail else ""))
        if not any(i["ok"] for i in p["services"].values()):
            lines += ["", "Nothing is authorised yet. Run:  pa auth login"]
        return lines

    output.emit(payload, render)


def cmd_logout(args):
    account = config.resolve_account(args.account)
    removed = auth.logout(account)
    output.emit(
        {"account": account, "removed": removed},
        lambda p: [f"Removed stored token for '{p['account']}'." if p["removed"]
                   else f"No stored token for '{p['account']}' (legacy MCP creds, if any, "
                        "are left untouched)."],
    )


def cmd_accounts(args):
    accounts = config.list_accounts()
    default = config.resolve_account(None)
    output.emit(
        {"accounts": accounts, "default": default},
        lambda p: ([f"{'*' if a == p['default'] else ' '} {a}" for a in p["accounts"]]
                   or ["No accounts stored. Run: pa auth login"]),
    )


def cmd_setup_client(args):
    """Install a downloaded Google OAuth client JSON into the right place."""
    source = Path(args.path).expanduser()
    if not source.exists():
        raise UsageError(f"No such file: {source}")
    # Validate before installing, so a wrong download fails loudly and early.
    auth._client_from_file(source)

    destination = (config.account_dir(config.resolve_account(args.account)) / "client.json"
                   if args.account else config.pa_home() / "client.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    output.emit({"installed": str(destination)},
                lambda p: [f"OAuth client installed at {p['installed']}.",
                           "Next:  pa auth login"])


def register(subparsers, common):
    parser = subparsers.add_parser("auth", help="Authorise Google access; inspect credentials")
    actions = parser.add_subparsers(dest="auth_command", required=True)

    p = actions.add_parser("login", parents=[common], help="Run the OAuth flow in a browser")
    p.add_argument("--service", action="append", choices=sorted(auth.SCOPES),
                   help="Limit consent to specific services (default: all)")
    p.add_argument("--force", action="store_true", help="Discard the existing token first")
    p.set_defaults(func=cmd_login)

    p = actions.add_parser("status", parents=[common], help="Show where credentials come from and whether they work")
    p.set_defaults(func=cmd_status)

    p = actions.add_parser("logout", parents=[common], help="Delete the stored token for an account")
    p.set_defaults(func=cmd_logout)

    p = actions.add_parser("accounts", parents=[common], help="List configured accounts")
    p.set_defaults(func=cmd_accounts)

    p = actions.add_parser("setup-client", parents=[common], help="Install a downloaded OAuth client JSON")
    p.add_argument("path", help="Path to the client_secret_*.json you downloaded")
    p.set_defaults(func=cmd_setup_client)
