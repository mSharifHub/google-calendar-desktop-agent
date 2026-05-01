"""
Unified calendar layer that merges events from all connected providers,
detects conflicts, and suggests resolutions.
"""
import datetime
from dataclasses import dataclass
from typing import List, Tuple
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

DISPLAY_TZ = ZoneInfo("America/Los_Angeles")

# Provider priority for conflict resolution (lower index = higher priority)
PROVIDER_PRIORITY = ["google", "outlook", "apple", "calendly"]


@dataclass
class UnifiedEvent:
    id: str
    title: str
    start: datetime.datetime
    end: datetime.datetime
    provider: str        # "google" | "outlook" | "apple" | "calendly"
    location: str = ""
    description: str = ""

    def to_str(self) -> str:
        loc = f" @ {self.location}" if self.location else ""
        start_local = self.start.astimezone(DISPLAY_TZ)
        end_local = self.end.astimezone(DISPLAY_TZ)
        return (
            f"[{self.provider.upper()}] {self.title}{loc}\n"
            f"  Start : {start_local.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
            f"  End   : {end_local.strftime('%Y-%m-%d %I:%M %p %Z')}\n"
            f"  ID    : {self.id}"
        )


# ---------- helpers ----------

def _to_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _parse_dt(raw: str) -> datetime.datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return datetime.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")


# ---------- per-provider fetchers ----------

def _fetch_google(days: int) -> List[UnifiedEvent]:
    print(f"[UNIFIED] _fetch_google() called → days={days}")
    try:
        from auth.google_auth import is_connected, get_service
        if not is_connected():
            print("[UNIFIED] _fetch_google() → Google not connected, skipping")
            return []
        service = get_service("calendar", "v3")
        now = datetime.datetime.now(datetime.timezone.utc)
        end = now + datetime.timedelta(days=days)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=100,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        out = []
        for e in result.get("items", []):
            s = e["start"].get("dateTime", e["start"].get("date", ""))
            en = e["end"].get("dateTime", e["end"].get("date", ""))
            try:
                out.append(UnifiedEvent(
                    id=e.get("id", ""),
                    title=e.get("summary", "No title"),
                    start=_to_utc(_parse_dt(s)),
                    end=_to_utc(_parse_dt(en)),
                    provider="google",
                    location=e.get("location", ""),
                    description=e.get("description", ""),
                ))
            except Exception:
                continue
        print(f"[UNIFIED] _fetch_google() → fetched {len(out)} events")
        return out
    except Exception as e:
        print(f"[UNIFIED] _fetch_google() → error: {e}")
        return []


def _fetch_outlook(days: int) -> List[UnifiedEvent]:
    print(f"[UNIFIED] _fetch_outlook() called → days={days}")
    try:
        from auth.microsoft_auth import get_access_token, is_connected
        if not is_connected():
            print("[UNIFIED] _fetch_outlook() → Outlook not connected, skipping")
            return []
        import requests as http_requests
        token = get_access_token()
        now = datetime.datetime.now(datetime.timezone.utc)
        end = now + datetime.timedelta(days=days)
        resp = http_requests.get(
            "https://graph.microsoft.com/v1.0/me/calendarView",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "startDateTime": now.isoformat().replace("+00:00", "Z"),
                "endDateTime": end.isoformat().replace("+00:00", "Z"),
                "$top": 100,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location,bodyPreview",
            },
            timeout=15,
        )
        resp.raise_for_status()
        out = []
        for e in resp.json().get("value", []):
            try:
                out.append(UnifiedEvent(
                    id=e.get("id", ""),
                    title=e.get("subject", "No title"),
                    start=_to_utc(_parse_dt(e["start"]["dateTime"])),
                    end=_to_utc(_parse_dt(e["end"]["dateTime"])),
                    provider="outlook",
                    location=e.get("location", {}).get("displayName", ""),
                    description=e.get("bodyPreview", ""),
                ))
            except Exception:
                continue
        print(f"[UNIFIED] _fetch_outlook() → fetched {len(out)} events")
        return out
    except Exception as e:
        print(f"[UNIFIED] _fetch_outlook() → error: {e}")
        return []


def _fetch_apple(days: int) -> List[UnifiedEvent]:
    print(f"[UNIFIED] _fetch_apple() called → days={days}")
    try:
        from auth.apple_auth import get_apple_client, is_connected
        if not is_connected():
            print("[UNIFIED] _fetch_apple() → Apple not connected, skipping")
            return []
        client = get_apple_client()
        if not client:
            return []
        principal = client.principal()
        now = datetime.datetime.now(datetime.timezone.utc)
        end = now + datetime.timedelta(days=days)
        out = []
        for cal in principal.calendars():
            try:
                for ev in cal.date_search(start=now, end=end, expand=True):
                    try:
                        ical = ev.icalendar_instance
                    except Exception:
                        continue
                    for component in ical.walk("VEVENT"):
                        try:
                            summary = str(component.get("SUMMARY", "No title"))
                            ev_id = str(component.get("UID", ""))
                            dtstart = component.get("DTSTART").dt
                            dtend_prop = component.get("DTEND")
                            dtend = dtend_prop.dt if dtend_prop else dtstart + datetime.timedelta(hours=1)
                            # Ensure datetime (not date)
                            if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
                                dtstart = datetime.datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=datetime.timezone.utc)
                            if isinstance(dtend, datetime.date) and not isinstance(dtend, datetime.datetime):
                                dtend = datetime.datetime(dtend.year, dtend.month, dtend.day, tzinfo=datetime.timezone.utc)
                            location = str(component.get("LOCATION", ""))
                            out.append(UnifiedEvent(
                                id=ev_id,
                                title=summary,
                                start=_to_utc(dtstart),
                                end=_to_utc(dtend),
                                provider="apple",
                                location=location,
                            ))
                        except Exception as e:
                            print(f"[UNIFIED] _fetch_apple() → skipping VEVENT due to error: {e}")
                            continue
            except Exception as e:
                print(f"[UNIFIED] _fetch_apple() → skipping calendar due to error: {e}")
                continue
        print(f"[UNIFIED] _fetch_apple() → fetched {len(out)} events")
        return out
    except Exception as e:
        print(f"[UNIFIED] _fetch_apple() → error: {e}")
        return []


def _fetch_calendly(days: int) -> List[UnifiedEvent]:
    print(f"[UNIFIED] _fetch_calendly() called → days={days}")
    try:
        from auth.calendly_auth import get_calendly_token, is_connected
        if not is_connected():
            print("[UNIFIED] _fetch_calendly() → Calendly not connected, skipping")
            return []
        import requests as http_requests
        token = get_calendly_token()
        headers = {"Authorization": f"Bearer {token}"}
        user_uri = http_requests.get(
            "https://api.calendly.com/users/me", headers=headers, timeout=10
        ).json()["resource"]["uri"]
        now = datetime.datetime.now(datetime.timezone.utc)
        resp = http_requests.get(
            "https://api.calendly.com/scheduled_events",
            headers=headers,
            params={
                "user": user_uri,
                "count": 100,
                "status": "active",
                "sort": "start_time:asc",
                "min_start_time": now.isoformat().replace("+00:00", "Z"),
            },
            timeout=10,
        )
        resp.raise_for_status()
        out = []
        for e in resp.json().get("collection", []):
            try:
                out.append(UnifiedEvent(
                    id=e.get("uri", "").split("/")[-1],
                    title=e.get("name", "Meeting"),
                    start=_to_utc(_parse_dt(e["start_time"])),
                    end=_to_utc(_parse_dt(e["end_time"])),
                    provider="calendly",
                ))
            except Exception:
                continue
        print(f"[UNIFIED] _fetch_calendly() → fetched {len(out)} events")
        return out
    except Exception as e:
        print(f"[UNIFIED] _fetch_calendly() → error: {e}")
        return []


# ---------- public helpers (used by tools AND by server) ----------

def get_todays_events_all() -> List[UnifiedEvent]:
    """Fetch today's events from all connected providers, sorted by start time."""
    print("[UNIFIED] get_todays_events_all() called")
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    events = get_all_events(days_ahead=1)
    today_events = [e for e in events if e.start >= today_start and e.start <= today_end]
    print(f"[UNIFIED] get_todays_events_all() → {len(today_events)} events for today")
    return today_events


def get_all_events(days_ahead: int = 7) -> List[UnifiedEvent]:
    """Fetch and merge events from all connected providers, sorted by start time."""
    print(f"[UNIFIED] get_all_events() called → days_ahead={days_ahead}")
    events = (
        _fetch_google(days_ahead)
        + _fetch_outlook(days_ahead)
        + _fetch_apple(days_ahead)
        + _fetch_calendly(days_ahead)
    )
    sorted_events = sorted(events, key=lambda e: e.start)
    print(f"[UNIFIED] get_all_events() → total {len(sorted_events)} events across all providers")
    return sorted_events


def find_conflicts(events: List[UnifiedEvent]) -> List[Tuple[UnifiedEvent, UnifiedEvent]]:
    """Return pairs of events whose time ranges overlap."""
    pairs: List[Tuple[UnifiedEvent, UnifiedEvent]] = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.start < b.end and b.start < a.end:
                pairs.append((a, b))
    return pairs


# ---------- LangChain tools ----------

@tool
def edit_calendar_event(
    name_or_id: str,
    new_summary: str = None,
    new_start_time: str = None,
    new_end_time: str = None,
    new_description: str = None,
    new_location: str = None,
) -> str:
    """
    Find an event by name or ID across ALL connected calendar providers and edit it.
    ALWAYS use this tool when the user asks to change, update, reschedule, or rename any event —
    never call a provider-specific edit tool directly without first using this to locate the event.

    name_or_id: partial or full event name (case-insensitive) or exact event ID.
    new_start_time / new_end_time: ISO 8601 strings, e.g. '2026-05-01T21:00:00'.
    Only supply fields you want to change; omit the rest.
    """
    print(f"[TOOL:unified] edit_calendar_event() called → name_or_id={name_or_id!r}")
    events = get_all_events(days_ahead=60)

    # 1. Exact ID match
    matches = [e for e in events if e.id == name_or_id]
    # 2. Case-insensitive name match
    if not matches:
        matches = [e for e in events if name_or_id.lower() in e.title.lower()]

    print(f"[TOOL:unified] edit_calendar_event() → found {len(matches)} match(es)")

    if not matches:
        return f"No event found matching '{name_or_id}' across any connected calendar."

    if len(matches) > 1:
        lines = [f"Multiple events match '{name_or_id}'. Which one should be edited?"]
        for e in matches:
            lines.append(f"  [{e.provider.upper()}] {e.title} — {e.start.date()} — ID: {e.id}")
        return "\n".join(lines)

    event = matches[0]
    print(f"[TOOL:unified] edit_calendar_event() → routing edit to provider={event.provider!r}, id={event.id}")

    if event.provider == "google":
        try:
            from auth.google_auth import get_service
            service = get_service("calendar", "v3")
            body = service.events().get(calendarId="primary", eventId=event.id).execute()
            if new_summary is not None:
                body["summary"] = new_summary
            if new_description is not None:
                body["description"] = new_description
            if new_location is not None:
                body["location"] = new_location
            if new_start_time is not None:
                body["start"] = {"dateTime": new_start_time, "timeZone": "America/Los_Angeles"}
            if new_end_time is not None:
                body["end"] = {"dateTime": new_end_time, "timeZone": "America/Los_Angeles"}
            updated = service.events().update(calendarId="primary", eventId=event.id, body=body).execute()
            print(f"[TOOL:unified] edit_calendar_event() → Google event updated: {updated.get('summary')!r}")
            return f"Updated '{event.title}' in Google Calendar. Link: {updated.get('htmlLink')}"
        except Exception as e:
            print(f"[TOOL:unified] edit_calendar_event() → Google edit error: {e}")
            return f"Error editing Google Calendar event: {e}"

    elif event.provider == "outlook":
        try:
            import requests as http_requests
            from auth.microsoft_auth import get_access_token
            token = get_access_token()
            if not token:
                return "Outlook is not connected."
            patch: dict = {}
            if new_summary is not None:
                patch["subject"] = new_summary
            if new_start_time is not None:
                patch["start"] = {"dateTime": new_start_time, "timeZone": "America/Los_Angeles"}
            if new_end_time is not None:
                patch["end"] = {"dateTime": new_end_time, "timeZone": "America/Los_Angeles"}
            if new_description is not None:
                patch["body"] = {"contentType": "text", "content": new_description}
            if new_location is not None:
                patch["location"] = {"displayName": new_location}
            resp = http_requests.patch(
                f"https://graph.microsoft.com/v1.0/me/events/{event.id}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=patch,
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[TOOL:unified] edit_calendar_event() → Outlook event updated: {event.title!r}")
            return f"Updated '{event.title}' in Outlook Calendar."
        except Exception as e:
            print(f"[TOOL:unified] edit_calendar_event() → Outlook edit error: {e}")
            return f"Error editing Outlook event: {e}"

    elif event.provider == "apple":
        # CalDAV edit = delete old + create new with same UID
        try:
            import icalendar
            import uuid as _uuid
            import datetime as _dt
            from auth.apple_auth import get_apple_client
            client = get_apple_client()
            if not client:
                return "Apple Calendar is not connected."
            principal = client.principal()
            search_start = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=365)
            search_end = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=730)
            for cal in principal.calendars():
                try:
                    for ev in cal.date_search(start=search_start, end=search_end, expand=True):
                        try:
                            ical = ev.icalendar_instance
                            for component in ical.walk("VEVENT"):
                                uid = str(component.get("UID", ""))
                                if uid != event.id:
                                    continue
                                # Apply changes to the component
                                if new_summary is not None:
                                    component["SUMMARY"] = new_summary
                                def _to_dt(iso: str) -> _dt.datetime:
                                    return _dt.datetime.fromisoformat(iso)
                                if new_start_time is not None:
                                    component["DTSTART"] = icalendar.vDatetime(_to_dt(new_start_time))
                                if new_end_time is not None:
                                    component["DTEND"] = icalendar.vDatetime(_to_dt(new_end_time))
                                if new_description is not None:
                                    component["DESCRIPTION"] = new_description
                                if new_location is not None:
                                    component["LOCATION"] = new_location
                                ev.delete()
                                cal.save_event(ical.to_ical().decode())
                                print(f"[TOOL:unified] edit_calendar_event() → Apple event updated: {event.title!r}")
                                return f"Updated '{event.title}' in Apple Calendar."
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[TOOL:unified] edit_calendar_event() → skipping Apple calendar: {e}")
                    continue
            return f"Could not find '{event.title}' in Apple Calendar to edit."
        except Exception as e:
            print(f"[TOOL:unified] edit_calendar_event() → Apple edit error: {e}")
            return f"Error editing Apple Calendar event: {e}"

    else:
        return f"Editing is not supported for provider '{event.provider}'."


@tool
def delete_calendar_event(name_or_id: str) -> str:
    """
    Find an event by name or ID across ALL connected calendar providers and delete it.
    ALWAYS use this tool when the user asks to delete, remove, or cancel any event —
    never call a provider-specific delete tool directly without first using this to locate the event.

    name_or_id can be:
      - A partial or full event name (case-insensitive match)
      - An exact event ID / UID from any provider
    """
    print(f"[TOOL:unified] delete_calendar_event() called → name_or_id={name_or_id!r}")
    events = get_all_events(days_ahead=60)

    # 1. Exact ID match
    matches = [e for e in events if e.id == name_or_id]
    # 2. Case-insensitive name match
    if not matches:
        matches = [e for e in events if name_or_id.lower() in e.title.lower()]

    print(f"[TOOL:unified] delete_calendar_event() → found {len(matches)} match(es)")

    if not matches:
        return f"No event found matching '{name_or_id}' across any connected calendar."

    if len(matches) > 1:
        lines = [f"Multiple events match '{name_or_id}'. Which one should be deleted?"]
        for e in matches:
            lines.append(f"  [{e.provider.upper()}] {e.title} — {e.start.date()} — ID: {e.id}")
        return "\n".join(lines)

    event = matches[0]
    print(f"[TOOL:unified] delete_calendar_event() → routing delete to provider={event.provider!r}, id={event.id}")

    if event.provider == "google":
        try:
            from auth.google_auth import get_service
            service = get_service("calendar", "v3")
            service.events().delete(calendarId="primary", eventId=event.id).execute()
            print(f"[TOOL:unified] delete_calendar_event() → Google event deleted: {event.title!r}")
            return f"Deleted '{event.title}' from Google Calendar."
        except Exception as e:
            print(f"[TOOL:unified] delete_calendar_event() → Google delete error: {e}")
            return f"Error deleting Google Calendar event: {e}"

    elif event.provider == "outlook":
        try:
            import requests as http_requests
            from auth.microsoft_auth import get_access_token
            token = get_access_token()
            if not token:
                return "Outlook is not connected."
            resp = http_requests.delete(
                f"https://graph.microsoft.com/v1.0/me/events/{event.id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[TOOL:unified] delete_calendar_event() → Outlook event deleted: {event.title!r}")
            return f"Deleted '{event.title}' from Outlook Calendar."
        except Exception as e:
            print(f"[TOOL:unified] delete_calendar_event() → Outlook delete error: {e}")
            return f"Error deleting Outlook event: {e}"

    elif event.provider == "apple":
        try:
            from auth.apple_auth import get_apple_client
            import datetime as _dt
            client = get_apple_client()
            if not client:
                return "Apple Calendar is not connected."
            principal = client.principal()
            # iCloud doesn't support UID-based REPORT queries reliably,
            # so we do a broad date search and match by UID from parsed icalendar data.
            search_start = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=365)
            search_end = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=730)
            print(f"[TOOL:unified] delete_calendar_event() → scanning Apple calendars for UID={event.id}")
            for cal in principal.calendars():
                try:
                    for ev in cal.date_search(start=search_start, end=search_end, expand=True):
                        try:
                            ical = ev.icalendar_instance
                            for component in ical.walk("VEVENT"):
                                uid = str(component.get("UID", ""))
                                if uid == event.id:
                                    ev.delete()
                                    print(f"[TOOL:unified] delete_calendar_event() → Apple event deleted: {event.title!r}")
                                    return f"Deleted '{event.title}' from Apple Calendar."
                        except Exception:
                            continue
                except Exception as e:
                    print(f"[TOOL:unified] delete_calendar_event() → skipping Apple calendar: {e}")
                    continue
            print(f"[TOOL:unified] delete_calendar_event() → Apple event not found by UID scan")
            return f"Could not find '{event.title}' in Apple Calendar to delete."
        except Exception as e:
            print(f"[TOOL:unified] delete_calendar_event() → Apple delete error: {e}")
            return f"Error deleting Apple Calendar event: {e}"

    else:
        return f"Deletion is not supported for provider '{event.provider}'."


@tool
def sync_todays_events() -> str:
    """
    Fetch and display TODAY's events from all connected calendar providers (Google, Outlook,
    Apple, Calendly) merged into one chronological view.
    Call this when the user asks what's on their calendar today, what their day looks like,
    or any variation of showing today's schedule.
    """
    print("[TOOL:unified] sync_todays_events() called")
    events = get_todays_events_all()
    if not events:
        print("[TOOL:unified] sync_todays_events() → no events found for today")
        return "No events found across any connected calendar for today."
    print(f"[TOOL:unified] sync_todays_events() → returning {len(events)} events")
    lines = ["=== Today's Unified Calendar ===\n"]
    lines += [e.to_str() + "\n" for e in events]
    return "\n".join(lines)


@tool
def sync_all_calendars(days_ahead: int = 7) -> str:
    """
    Fetch and display events from all connected calendar providers (Google, Outlook, Apple,
    Calendly) merged into one chronological view.
    Call this when the user wants their full schedule across all calendars.
    """
    print(f"[TOOL:unified] sync_all_calendars() called → days_ahead={days_ahead}")
    events = get_all_events(days_ahead)
    if not events:
        print("[TOOL:unified] sync_all_calendars() → no events found")
        return "No events found across any connected calendar for the next {} days.".format(days_ahead)
    print(f"[TOOL:unified] sync_all_calendars() → returning {len(events)} events")
    lines = [f"=== Unified Calendar — next {days_ahead} day(s) ===\n"]
    lines += [e.to_str() + "\n" for e in events]
    return "\n".join(lines)


@tool
def find_calendar_conflicts(days_ahead: int = 7) -> str:
    """
    Find scheduling conflicts (overlapping events) across all connected calendar providers.
    Returns each conflicting pair with provider, title, and time details.
    """
    print(f"[TOOL:unified] find_calendar_conflicts() called → days_ahead={days_ahead}")
    events = get_all_events(days_ahead)
    conflicts = find_conflicts(events)
    print(f"[TOOL:unified] find_calendar_conflicts() → found {len(conflicts)} conflict(s)")
    if not conflicts:
        return f"No scheduling conflicts found in the next {days_ahead} day(s). ✓"
    lines = [f"Found {len(conflicts)} conflict(s) in the next {days_ahead} day(s):\n"]
    for i, (a, b) in enumerate(conflicts, 1):
        lines.append(f"Conflict {i}:")
        lines.append(f"  {a.to_str()}")
        lines.append(f"  {b.to_str()}\n")
    return "\n".join(lines)


@tool
def resolve_calendar_conflicts(days_ahead: int = 7, strategy: str = "priority") -> str:
    """
    Analyse conflicts across all connected calendars and suggest resolutions.

    strategy options:
      - "priority"  : Prefer the provider with higher trust (Google > Outlook > Apple > Calendly).
      - "shorter"   : Keep the shorter/more-specific event; flag the longer one for rescheduling.
      - "report"    : List conflicts only — no recommendation is made.

    Returns a plain-text report with one recommendation per conflict.
    """
    print(f"[TOOL:unified] resolve_calendar_conflicts() called → days_ahead={days_ahead}, strategy={strategy!r}")
    events = get_all_events(days_ahead)
    conflicts = find_conflicts(events)
    print(f"[TOOL:unified] resolve_calendar_conflicts() → {len(conflicts)} conflict(s) to resolve")
    if not conflicts:
        return f"No conflicts to resolve in the next {days_ahead} day(s). ✓"

    lines = [f"Conflict resolution report ({strategy} strategy, next {days_ahead} day(s)):\n"]
    for i, (a, b) in enumerate(conflicts, 1):
        lines.append(f"Conflict {i}:")
        fmt = lambda dt: dt.astimezone(DISPLAY_TZ).strftime('%Y-%m-%d %I:%M %p %Z')
        lines.append(f"  A: [{a.provider.upper()}] {a.title}  ({fmt(a.start)} – {fmt(a.end)})")
        lines.append(f"  B: [{b.provider.upper()}] {b.title}  ({fmt(b.start)} – {fmt(b.end)})")

        if strategy == "priority":
            pa = PROVIDER_PRIORITY.index(a.provider) if a.provider in PROVIDER_PRIORITY else 99
            pb = PROVIDER_PRIORITY.index(b.provider) if b.provider in PROVIDER_PRIORITY else 99
            keep, reschedule = (a, b) if pa <= pb else (b, a)
            lines.append(f"  → Keep      : [{keep.provider.upper()}] {keep.title}")
            lines.append(f"  → Reschedule: [{reschedule.provider.upper()}] {reschedule.title}\n")
        elif strategy == "shorter":
            dur_a = (a.end - a.start).total_seconds()
            dur_b = (b.end - b.start).total_seconds()
            keep, reschedule = (a, b) if dur_a <= dur_b else (b, a)
            lines.append(f"  → Keep (shorter): [{keep.provider.upper()}] {keep.title}")
            lines.append(f"  → Reschedule    : [{reschedule.provider.upper()}] {reschedule.title}\n")
        else:
            lines.append("  → Manual review required.\n")

    return "\n".join(lines)
