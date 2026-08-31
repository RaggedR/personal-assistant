"""Google Contacts (People API) subcommands.

The People API splits your address book in two: saved *contacts*, and *other
contacts* — addresses harvested from mail you have exchanged but never saved.
Most work colleagues live in the second bucket, so every search here queries
both and merges the results.

``searchContacts`` is also cache-backed: Google requires a "warmup" request
with an empty query before the first real search, otherwise it returns nothing.
``_warmup`` handles that so callers never see the empty-first-result surprise.
"""

from __future__ import annotations

from googleapiclient.errors import HttpError

from .. import output, services
from ..errors import NotFoundError

CONTACT_FIELDS = "names,emailAddresses,phoneNumbers,organizations"
OTHER_FIELDS = "names,emailAddresses"


def _api(args):
    return services.service("contacts", getattr(args, "account", None))


def _flatten(person: dict) -> dict:
    names = person.get("names") or []
    emails = person.get("emailAddresses") or []
    phones = person.get("phoneNumbers") or []
    orgs = person.get("organizations") or []
    return {
        "resource_name": person.get("resourceName"),
        "name": names[0].get("displayName") if names else "",
        "emails": [e.get("value") for e in emails if e.get("value")],
        "primary_email": next(
            (e.get("value") for e in emails if (e.get("metadata") or {}).get("primary")),
            emails[0].get("value") if emails else None,
        ),
        "phones": [p.get("value") for p in phones if p.get("value")],
        "organisation": orgs[0].get("name") if orgs else "",
        "title": orgs[0].get("title") if orgs else "",
    }


def _warmup(api) -> None:
    """Prime the server-side search cache; failures are not fatal."""
    for call, fields in (
        (api.people().searchContacts, CONTACT_FIELDS),
        (api.otherContacts().search, OTHER_FIELDS),
    ):
        try:
            call(query="", readMask=fields, pageSize=1).execute()
        except HttpError:
            pass


def _search(api, query: str, limit: int) -> list[dict]:
    found: dict[str, dict] = {}

    try:
        saved = api.people().searchContacts(
            query=query, readMask=CONTACT_FIELDS, pageSize=min(limit, 30)
        ).execute()
        for hit in saved.get("results", []):
            record = _flatten(hit.get("person", {}))
            record["source"] = "contact"
            found[record["resource_name"] or record["name"]] = record
    except HttpError as exc:
        if getattr(getattr(exc, "resp", None), "status", None) not in (400, 403):
            raise services.translate(exc) from exc

    try:
        other = api.otherContacts().search(
            query=query, readMask=OTHER_FIELDS, pageSize=min(limit, 30)
        ).execute()
        for hit in other.get("results", []):
            record = _flatten(hit.get("person", {}))
            record["source"] = "other"
            found.setdefault(record["resource_name"] or record["name"], record)
    except HttpError as exc:
        if getattr(getattr(exc, "resp", None), "status", None) not in (400, 403):
            raise services.translate(exc) from exc

    return [r for r in found.values() if r["emails"]][:limit]


def _render_rows(records: list[dict]) -> list[str]:
    rows = [[r.get("source", ""), r["name"], r["primary_email"] or "",
             r.get("organisation", "")] for r in records]
    return output.table(rows, headers=["SOURCE", "NAME", "EMAIL", "ORG"])


def cmd_search(args):
    api = _api(args)
    _warmup(api)
    records = _search(api, args.query, args.limit)

    def render(payload):
        if not payload["contacts"]:
            return [f"No contacts matched {payload['query']!r}."]
        return _render_rows(payload["contacts"])

    output.emit({"query": args.query, "count": len(records), "contacts": records}, render)


def cmd_resolve(args):
    """Return the single best email for a name — built for scripting.

    Exits 4 when nothing matches, so a caller can branch on the exit code
    rather than parsing output.
    """
    api = _api(args)
    _warmup(api)
    records = _search(api, args.query, 10)
    if not records:
        raise NotFoundError(f"No contact found matching {args.query!r}")

    lowered = args.query.lower()
    records.sort(key=lambda r: (
        0 if lowered in (r["name"] or "").lower() else 1,
        0 if r.get("source") == "contact" else 1,
    ))
    best = records[0]

    output.emit(
        {"query": args.query, "name": best["name"], "email": best["primary_email"],
         "alternatives": [r["primary_email"] for r in records[1:]]},
        lambda p: [p["email"]],
    )


def cmd_list(args):
    api = _api(args)
    records, token = [], None
    while len(records) < args.limit:
        try:
            page = api.people().connections().list(
                resourceName="people/me",
                personFields=CONTACT_FIELDS,
                pageSize=min(200, args.limit - len(records)),
                pageToken=token,
                sortOrder="LAST_MODIFIED_DESCENDING",
            ).execute()
        except HttpError as exc:
            raise services.translate(exc) from exc
        for person in page.get("connections", []):
            record = _flatten(person)
            record["source"] = "contact"
            records.append(record)
        token = page.get("nextPageToken")
        if not token:
            break

    output.emit({"count": len(records), "contacts": records},
                lambda p: _render_rows(p["contacts"]) or ["No saved contacts."])


def register(subparsers, common):
    contacts = subparsers.add_parser("contacts", help="Contacts: search, resolve a name to an email")
    actions = contacts.add_subparsers(dest="contacts_command", required=True)

    p = actions.add_parser("search", parents=[common], help="Search saved and 'other' contacts")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = actions.add_parser("resolve", parents=[common], help="Print the single best email for a name")
    p.add_argument("query")
    p.set_defaults(func=cmd_resolve)

    p = actions.add_parser("list", parents=[common], help="List saved contacts")
    p.add_argument("-n", "--limit", type=int, default=100)
    p.set_defaults(func=cmd_list)
