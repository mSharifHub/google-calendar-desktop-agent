import datetime
import uuid
from typing import Optional
from langchain_core.tools import tool


def _get_calendars():
    print("[TOOL:apple] _get_calendars() → fetching Apple CalDAV client")
    from auth.apple_auth import get_apple_client
    client = get_apple_client()
    if not client:
        print("[TOOL:apple] _get_calendars() → RuntimeError: not connected")
        raise RuntimeError(
            "Apple Calendar not connected. Ask the user to connect their iCloud account "
            "in the Calendar Providers settings."
        )
    calendars = client.principal().calendars()
    print(f"[TOOL:apple] _get_calendars() → found {len(calendars)} calendar(s)")
    return calendars


@tool
def get_apple_upcoming_events(max_results: int = 10) -> str:
    """Get upcoming events from Apple Calendar (iCloud CalDAV)."""
    print(f"[TOOL:apple] get_apple_upcoming_events() called → max_results={max_results}")
    try:
        calendars = _get_calendars()
        now = datetime.datetime.now(datetime.timezone.utc)
        end = now + datetime.timedelta(days=30)
        lines = []
        for cal in calendars:
            try:
                for ev in cal.date_search(start=now, end=end, expand=True):
                    try:
                        ical = ev.icalendar_instance
                    except Exception:
                        continue
                    for component in ical.walk("VEVENT"):
                        try:
                            summary = str(component.get("SUMMARY", "No title"))
                            ev_id = str(component.get("UID", "unknown"))
                            dtstart = component.get("DTSTART").dt
                            lines.append(f"- [ID: {ev_id}] {summary} at {dtstart}")
                            if len(lines) >= max_results:
                                break
                        except Exception:
                            continue
                    if len(lines) >= max_results:
                        break
            except Exception as e:
                print(f"[TOOL:apple] get_apple_upcoming_events() → skipping calendar due to error: {e}")
                continue
        print(f"[TOOL:apple] get_apple_upcoming_events() → fetched {len(lines)} events")
        return "\n".join(lines) if lines else "No upcoming Apple Calendar events found."
    except RuntimeError as e:
        print(f"[TOOL:apple] get_apple_upcoming_events() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:apple] get_apple_upcoming_events() → error: {e}")
        return f"Error fetching Apple events: {e}"


@tool
def get_apple_todays_events() -> str:
    """Get today's events from Apple Calendar (iCloud CalDAV)."""
    print("[TOOL:apple] get_apple_todays_events() called")
    try:
        calendars = _get_calendars()
        local_tz = datetime.timezone(datetime.timedelta(hours=-7))
        today = datetime.datetime.now(local_tz).date()
        start = datetime.datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=datetime.timezone.utc)
        end = datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=datetime.timezone.utc)
        print(f"[TOOL:apple] get_apple_todays_events() → querying for {today}")
        lines = []
        for cal in calendars:
            try:
                for ev in cal.date_search(start=start, end=end, expand=True):
                    try:
                        ical = ev.icalendar_instance
                    except Exception:
                        continue
                    for component in ical.walk("VEVENT"):
                        try:
                            summary = str(component.get("SUMMARY", "No title"))
                            ev_id = str(component.get("UID", "unknown"))
                            dtstart = component.get("DTSTART").dt
                            lines.append(f"- [ID: {ev_id}] {summary} at {dtstart}")
                        except Exception:
                            continue
            except Exception as e:
                print(f"[TOOL:apple] get_apple_todays_events() → skipping calendar due to error: {e}")
                continue
        print(f"[TOOL:apple] get_apple_todays_events() → fetched {len(lines)} events for {today}")
        return "\n".join(lines) if lines else f"No Apple Calendar events for today ({today})."
    except RuntimeError as e:
        print(f"[TOOL:apple] get_apple_todays_events() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:apple] get_apple_todays_events() → error: {e}")
        return f"Error fetching Apple events: {e}"


@tool
def delete_apple_event(event_uid: str) -> str:
    """Delete an Apple Calendar (iCloud CalDAV) event by its UID."""
    print(f"[TOOL:apple] delete_apple_event() called → event_uid={event_uid}")
    try:
        from auth.apple_auth import get_apple_client
        client = get_apple_client()
        if not client:
            return "Apple Calendar is not connected."
        principal = client.principal()
        # iCloud doesn't support UID-based REPORT queries reliably,
        # so scan a broad date range and match by UID from parsed icalendar data.
        search_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)
        search_end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=730)
        print(f"[TOOL:apple] delete_apple_event() → scanning calendars for UID={event_uid}")
        for cal in principal.calendars():
            try:
                for ev in cal.date_search(start=search_start, end=search_end, expand=True):
                    try:
                        ical = ev.icalendar_instance
                        for component in ical.walk("VEVENT"):
                            uid = str(component.get("UID", ""))
                            if uid == event_uid:
                                ev.delete()
                                print(f"[TOOL:apple] delete_apple_event() → deleted UID={event_uid}")
                                return f"Apple Calendar event deleted successfully (UID: {event_uid})."
                    except Exception:
                        continue
            except Exception as e:
                print(f"[TOOL:apple] delete_apple_event() → skipping calendar due to error: {e}")
                continue
        print(f"[TOOL:apple] delete_apple_event() → event not found after full scan")
        return f"Apple Calendar event not found (UID: {event_uid})."
    except RuntimeError as e:
        print(f"[TOOL:apple] delete_apple_event() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:apple] delete_apple_event() → error: {e}")
        return f"Error deleting Apple Calendar event: {e}"


@tool
def create_apple_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Create a new event in Apple Calendar (iCloud CalDAV).
    start_time and end_time must be ISO 8601 strings (e.g. '2026-04-28T14:30:00').
    """
    print(f"[TOOL:apple] create_apple_event() called → summary={summary!r}, start={start_time}, end={end_time}")
    try:
        import icalendar  # pip install icalendar
        calendars = _get_calendars()
        if not calendars:
            print("[TOOL:apple] create_apple_event() → no calendars found")
            return "No Apple calendars found."

        cal_obj = icalendar.Calendar()
        cal_obj.add("prodid", "-//Calendar Assistant//EN")
        cal_obj.add("version", "2.0")

        event = icalendar.Event()
        event.add("summary", summary)
        event.add("uid", str(uuid.uuid4()))
        event.add("dtstart", datetime.datetime.fromisoformat(start_time))
        event.add("dtend", datetime.datetime.fromisoformat(end_time))
        if description:
            event.add("description", description)
        if location:
            event.add("location", location)

        cal_obj.add_component(event)
        ical_data = cal_obj.to_ical().decode()

        # Try each calendar until one accepts the write (some are read-only)
        last_error = None
        for target_cal in calendars:
            try:
                cal_name = str(getattr(target_cal, 'name', target_cal))
                print(f"[TOOL:apple] create_apple_event() → trying calendar: {cal_name}")
                target_cal.save_event(ical_data)
                print(f"[TOOL:apple] create_apple_event() → event created in: {cal_name}")
                return f"Apple Calendar event created: '{summary}'"
            except Exception as e:
                print(f"[TOOL:apple] create_apple_event() → calendar {cal_name!r} rejected: {e}")
                last_error = e
                continue

        print(f"[TOOL:apple] create_apple_event() → all calendars rejected the event")
        return f"Error creating Apple event: {last_error}"
    except RuntimeError as e:
        print(f"[TOOL:apple] create_apple_event() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:apple] create_apple_event() → error: {e}")
        return f"Error creating Apple event: {e}"
