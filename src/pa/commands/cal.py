"""Google Calendar subcommands.

Two recurring subtleties are handled centrally here:

* All-day events use ``date``; timed events use ``dateTime`` + ``timeZone``.
  Mixing them produces confusing 400s, so ``_time_field`` picks one.
* ``singleEvents=True`` expands recurring series into concrete instances, which
  is almost always what "what's on next week" means. The instance id differs
  from the series id, which matters when updating or deleting.
"""

from __future__ import annotations

from googleapiclient.errors import HttpError

from .. import output, services, timeparse
from ..errors import ConfirmationRequired, UsageError


def _api(args):
    return services.service("calendar", getattr(args, "account", None))


def _calendar_id(args) -> str:
    return getattr(args, "calendar", None) or "primary"


def _time_field(value: str, all_day: bool) -> dict:
    dt = timeparse.parse(value)
    if all_day:
        return {"date": dt.date().isoformat()}
    return {"dateTime": timeparse.to_rfc3339(dt), "timeZone": str(timeparse.tzinfo())}


def _attendees(raw: list[str] | None) -> list[dict]:
    people = []
    for chunk in raw or []:
        people.extend({"email": part.strip()} for part in chunk.split(",") if part.strip())
    return people


def _flatten(event: dict) -> dict:
    start = event.get("start", {}) or {}
    end = event.get("end", {}) or {}
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "(untitled)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "status": event.get("status"),
        "organizer": (event.get("organizer") or {}).get("email", ""),
        "attendees": [
            {"email": a.get("email"), "response": a.get("responseStatus")}
            for a in event.get("attendees", []) or []
        ],
        "hangout_link": event.get("hangoutLink", ""),
        "html_link": event.get("htmlLink", ""),
        "recurring_event_id": event.get("recurringEventId"),
    }


def cmd_calendars(args):
    api = _api(args)
    items = api.calendarList().list().execute().get("items", [])
    records = [{
        "id": c.get("id"),
        "summary": c.get("summary"),
        "primary": bool(c.get("primary")),
        "access_role": c.get("accessRole"),
        "timezone": c.get("timeZone"),
    } for c in items]

    def render(payload):
        rows = [["*" if c["primary"] else " ", c["access_role"], c["summary"], c["id"]]
                for c in payload["calendars"]]
        return output.table(rows, headers=["", "ACCESS", "NAME", "ID"])

    output.emit({"calendars": records}, render)


def cmd_list(args):
    api = _api(args)
    lower, upper = timeparse.parse_range(args.start, args.end, default_days=args.days)
    try:
        result = api.events().list(
            calendarId=_calendar_id(args),
            timeMin=timeparse.to_rfc3339(lower),
            timeMax=timeparse.to_rfc3339(upper),
            singleEvents=True,
            orderBy="startTime",
            maxResults=args.limit,
            q=args.query,
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc
    events = [_flatten(e) for e in result.get("items", [])]

    def render(payload):
        if not payload["events"]:
            return [f"Nothing scheduled between {timeparse.humanise(payload['from'])} "
                    f"and {timeparse.humanise(payload['to'])}."]
        rows = []
        last_day = None
        for event in payload["events"]:
            day = (event["start"] or "")[:10]
            label = timeparse.humanise(event["start"]) if day != last_day else ""
            last_day = day
            when = "all day" if event["all_day"] else timeparse.humanise(event["start"])[-5:]
            rows.append([label, when, output.truncate(event["summary"], 42),
                         output.truncate(event["location"], 18), event["id"]])
        return output.table(rows, headers=["DAY", "TIME", "EVENT", "WHERE", "ID"])

    output.emit({"from": timeparse.to_rfc3339(lower), "to": timeparse.to_rfc3339(upper),
                 "calendar": _calendar_id(args), "count": len(events), "events": events}, render)


def cmd_show(args):
    api = _api(args)
    try:
        event = api.events().get(calendarId=_calendar_id(args), eventId=args.id).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    def render(e):
        lines = [
            f"Title:    {e['summary']}",
            f"When:     {timeparse.humanise(e['start'])} → {timeparse.humanise(e['end'])}"
            + (" (all day)" if e["all_day"] else ""),
            f"Status:   {e['status']}",
            f"Id:       {e['id']}",
        ]
        if e["location"]:
            lines.append(f"Where:    {e['location']}")
        if e["hangout_link"]:
            lines.append(f"Meet:     {e['hangout_link']}")
        if e["organizer"]:
            lines.append(f"Organiser:{e['organizer']}")
        for person in e["attendees"]:
            lines.append(f"  - {person['email']} ({person['response']})")
        if e["description"]:
            lines += ["", e["description"]]
        return lines

    output.emit(_flatten(event), render)


def cmd_create(args):
    api = _api(args)
    if not args.end and not args.duration:
        raise UsageError("Provide --end or --duration (e.g. --duration 60)")

    start_dt = timeparse.parse(args.start)
    if args.end:
        end_value = args.end
    else:
        from datetime import timedelta

        end_value = (start_dt + timedelta(minutes=args.duration)).isoformat()

    body = {
        "summary": args.title,
        "start": _time_field(args.start, args.all_day),
        "end": _time_field(end_value, args.all_day),
    }
    if args.location:
        body["location"] = args.location
    if args.description:
        body["description"] = args.description
    if args.attendee:
        body["attendees"] = _attendees(args.attendee)

    try:
        event = api.events().insert(
            calendarId=_calendar_id(args),
            body=body,
            sendUpdates="all" if args.notify else "none",
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    record = _flatten(event)

    def render(e):
        return ["Event created.",
                f"  {e['summary']}",
                f"  {timeparse.humanise(e['start'])} → {timeparse.humanise(e['end'])}",
                f"  id: {e['id']}"]

    output.emit(record, render)


def cmd_update(args):
    api = _api(args)
    calendar_id = _calendar_id(args)
    try:
        existing = api.events().get(calendarId=calendar_id, eventId=args.id).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    all_day = "date" in (existing.get("start") or {})
    patch = {}
    if args.title:
        patch["summary"] = args.title
    if args.location is not None:
        patch["location"] = args.location
    if args.description is not None:
        patch["description"] = args.description
    if args.start:
        patch["start"] = _time_field(args.start, all_day)
    if args.end:
        patch["end"] = _time_field(args.end, all_day)
    if args.attendee:
        patch["attendees"] = _attendees(args.attendee)
    if not patch:
        raise UsageError("Nothing to update — pass at least one field to change")

    try:
        event = api.events().patch(
            calendarId=calendar_id, eventId=args.id, body=patch,
            sendUpdates="all" if args.notify else "none",
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    output.emit(_flatten(event), lambda e: [
        "Event updated.",
        f"  {e['summary']}",
        f"  {timeparse.humanise(e['start'])} → {timeparse.humanise(e['end'])}",
    ])


def cmd_delete(args):
    api = _api(args)
    calendar_id = _calendar_id(args)
    try:
        existing = _flatten(
            api.events().get(calendarId=calendar_id, eventId=args.id).execute()
        )
    except HttpError as exc:
        raise services.translate(exc) from exc

    if not args.confirm:
        raise ConfirmationRequired(
            "Refusing to delete without --confirm.\n"
            f"  {existing['summary']}\n"
            f"  {timeparse.humanise(existing['start'])} → "
            f"{timeparse.humanise(existing['end'])}\n"
            f"To delete:  pa cal delete {args.id} --confirm"
        )
    try:
        api.events().delete(
            calendarId=calendar_id, eventId=args.id,
            sendUpdates="all" if args.notify else "none",
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    output.emit({"id": args.id, "deleted": True, "event": existing},
                lambda p: [f"Deleted: {p['event']['summary']}"])


def cmd_rsvp(args):
    """Set your own response on an event you were invited to."""
    api = _api(args)
    calendar_id = _calendar_id(args)
    try:
        event = api.events().get(calendarId=calendar_id, eventId=args.id).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    attendees = event.get("attendees", []) or []
    mine = [a for a in attendees if a.get("self")]
    if not mine:
        raise UsageError("You are not listed as an attendee on that event")
    for attendee in mine:
        attendee["responseStatus"] = args.response

    try:
        updated = api.events().patch(
            calendarId=calendar_id, eventId=args.id,
            body={"attendees": attendees}, sendUpdates="all",
        ).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    output.emit(_flatten(updated),
                lambda e: [f"RSVP set to '{args.response}' for {e['summary']}."])


def cmd_freebusy(args):
    api = _api(args)
    lower, upper = timeparse.parse_range(args.start, args.end, default_days=args.days)
    calendars = args.calendar or ["primary"]
    try:
        result = api.freebusy().query(body={
            "timeMin": timeparse.to_rfc3339(lower),
            "timeMax": timeparse.to_rfc3339(upper),
            "items": [{"id": c} for c in calendars],
        }).execute()
    except HttpError as exc:
        raise services.translate(exc) from exc

    def render(payload):
        lines = []
        for calendar_id, data in payload["calendars"].items():
            lines.append(f"{calendar_id}:")
            busy = data.get("busy", [])
            if not busy:
                lines.append("  free for the whole window")
            for block in busy:
                lines.append(f"  busy {timeparse.humanise(block['start'])} → "
                             f"{timeparse.humanise(block['end'])}")
        return lines

    output.emit({"from": timeparse.to_rfc3339(lower), "to": timeparse.to_rfc3339(upper),
                 "calendars": result.get("calendars", {})}, render)


def register(subparsers, common):
    cal = subparsers.add_parser("cal", help="Calendar: list, create, update, delete, free/busy")
    actions = cal.add_subparsers(dest="cal_command", required=True)

    common_calendar = dict(help="Calendar id (default: primary)")

    p = actions.add_parser("calendars", parents=[common], help="List calendars you can see")
    p.set_defaults(func=cmd_calendars)

    p = actions.add_parser("list", parents=[common], help="Agenda for a time range")
    p.add_argument("--from", dest="start", default=None, help="Range start (default: now)")
    p.add_argument("--to", dest="end", default=None, help="Range end")
    p.add_argument("--days", type=int, default=7, help="Window size when --to is omitted")
    p.add_argument("-n", "--limit", type=int, default=50)
    p.add_argument("-q", "--query", default=None, help="Free-text search within events")
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_list)

    p = actions.add_parser("show", parents=[common], help="Show one event in full")
    p.add_argument("id")
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_show)

    p = actions.add_parser("create", parents=[common], help="Create an event")
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True, help="e.g. '2026-09-02 14:00', 'tomorrow', '+2h'")
    p.add_argument("--end", default=None)
    p.add_argument("--duration", type=int, default=None, help="Minutes, as an --end alternative")
    p.add_argument("--all-day", action="store_true")
    p.add_argument("--location", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--attendee", action="append", help="Email (repeatable or comma-separated)")
    p.add_argument("--notify", action="store_true", help="Email invitations to attendees")
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_create)

    p = actions.add_parser("update", parents=[common], help="Change fields on an existing event")
    p.add_argument("id")
    p.add_argument("--title", default=None)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--attendee", action="append")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_update)

    p = actions.add_parser("delete", parents=[common], help="Delete an event (requires --confirm)")
    p.add_argument("id")
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--notify", action="store_true")
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_delete)

    p = actions.add_parser("rsvp", parents=[common], help="Respond to an invitation")
    p.add_argument("id")
    p.add_argument("--response", required=True,
                   choices=["accepted", "declined", "tentative", "needsAction"])
    p.add_argument("--calendar", **common_calendar)
    p.set_defaults(func=cmd_rsvp)

    p = actions.add_parser("freebusy", parents=[common], help="Show busy blocks for one or more calendars")
    p.add_argument("--from", dest="start", default=None)
    p.add_argument("--to", dest="end", default=None)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--calendar", action="append", help="Calendar id (repeatable)")
    p.set_defaults(func=cmd_freebusy)
