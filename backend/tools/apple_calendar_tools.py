import datetime
import uuid
import icalendar
import logging
from typing import Optional
from zoneinfo import ZoneInfo

from auth.apple_auth import get_apple_client, is_connected
from tools.unified_event import UnifiedEvent, _to_utc
from utils.retry import with_retry

LOCAL_TZ = ZoneInfo("America/Los_Angeles")

logger = logging.getLogger(__name__)

# Standard retry wrapper for API calls
_retry = lambda fn, *a, **kw: with_retry(fn, *a, label="[TOOL:apple]", **kw)


def _get_principal():
    """Helper to fetch the CalDAV principal."""
    client = get_apple_client()
    if not client:
        raise RuntimeError("Apple Calendar not connected.")
    return client.principal()


def fetch_apple_events(days: int) -> list[UnifiedEvent]:
    """Fetch events from Apple Calendar."""
    if not is_connected():
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=days)

    def _fetch():
        out = []
        principal = _get_principal()
        for cal in principal.calendars():
            try:
                # expand=False prevents the iCloud CalDAV empty-list bug
                for ev in cal.date_search(start=now, end=end, compfilter="VEVENT", expand=False):
                    try:
                        for component in ev.icalendar_instance.walk("VEVENT"):
                            dtstart = component.get("DTSTART").dt
                            dtend_prop = component.get("DTEND")
                            dtend = dtend_prop.dt if dtend_prop else dtstart + datetime.timedelta(hours=1)

                            # Handle all-day event normalization
                            is_all_day = isinstance(dtstart, datetime.date) and not isinstance(dtstart,
                                                                                               datetime.datetime)
                            if is_all_day:
                                dtstart = datetime.datetime(dtstart.year, dtstart.month, dtstart.day,
                                                            tzinfo=datetime.timezone.utc)
                                dtend = datetime.datetime(dtend.year, dtend.month, dtend.day,
                                                          tzinfo=datetime.timezone.utc)

                            out.append(UnifiedEvent(
                                id=str(component.get("UID", "")),
                                title=str(component.get("SUMMARY", "No title")),
                                start=_to_utc(dtstart),
                                end=_to_utc(dtend),
                                provider="apple",
                                location=str(component.get("LOCATION", "")),
                                is_all_day=is_all_day
                            ))
                    except Exception:
                        continue
            except Exception:
                continue
        return out

    try:
        return _retry(_fetch)
    except Exception as e:
        logger.error(f"Error fetching Apple events: {e}")
        return []


def create_apple_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None
) -> str:
    """Creates a new event in Apple Calendar (iCloud CalDAV)."""
    if not is_connected():
        return "Auth Error: Apple Calendar not connected."

    def _create():
        principal = _get_principal()

        # Build the iCalendar object
        cal_obj = icalendar.Calendar()
        cal_obj.add("prodid", "-//Calendar Assistant//EN")
        cal_obj.add("version", "2.0")

        event = icalendar.Event()
        event.add("summary", summary)
        event.add("uid", str(uuid.uuid4()))

        # Treat naive datetimes as local (Pacific) time, not UTC.
        # The agent always passes local times, e.g. "8:00 AM" means 8 AM PDT.
        start_dt = datetime.datetime.fromisoformat(start_time)
        end_dt = datetime.datetime.fromisoformat(end_time)
        if start_dt.tzinfo is None: start_dt = start_dt.replace(tzinfo=LOCAL_TZ)
        if end_dt.tzinfo is None: end_dt = end_dt.replace(tzinfo=LOCAL_TZ)

        event.add("dtstart", icalendar.vDatetime(start_dt))
        event.add("dtend", icalendar.vDatetime(end_dt))
        if description: event.add("description", description)
        if location: event.add("location", location)

        cal_obj.add_component(event)
        ical_data = cal_obj.to_ical().decode()

        # Prioritize "Home" calendar, fallback to first available
        target_cal = next((c for c in principal.calendars() if getattr(c, 'name', '').lower() == 'home'), None)
        if not target_cal:
            calendars = principal.calendars()
            if calendars: target_cal = calendars[0]

        if not target_cal:
            raise Exception("No Apple calendars found to save the event.")

        target_cal.save_event(ical_data)
        return str(getattr(target_cal, 'name', 'Unknown Calendar'))

    try:
        cal_name = _retry(_create)
        return f"Apple Calendar event created in {cal_name}: '{summary}'"
    except Exception as e:
        return f"Error creating Apple event: {e}"


def delete_apple_event(event_uid: str) -> str:
    """Deletes an Apple Calendar event by its UID."""
    if not is_connected():
        return "Auth Error: Apple Calendar not connected."

    def _delete():
        principal = _get_principal()
        search_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)
        search_end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=730)

        for cal in principal.calendars():
            try:
                for ev in cal.date_search(start=search_start, end=search_end, compfilter="VEVENT", expand=False):
                    try:
                        for component in ev.icalendar_instance.walk("VEVENT"):
                            if str(component.get("UID", "")) == event_uid:
                                ev.delete()
                                return f"Apple Calendar event deleted successfully (UID: {event_uid})."
                    except Exception:
                        continue
            except Exception:
                continue
        return f"Apple Calendar event not found (UID: {event_uid})."

    try:
        return _retry(_delete)
    except Exception as e:
        return f"Error deleting Apple event: {e}"


def edit_apple_event(
        event_uid: str,
        new_summary=None,
        new_start_time=None,
        new_end_time=None,
        new_description=None,
        new_location=None
) -> str:
    """Edits an existing Apple Calendar event."""
    if not is_connected():
        return "Auth Error: Apple Calendar not connected."

    def _edit():
        principal = _get_principal()
        search_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)
        search_end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=730)

        for cal in principal.calendars():
            try:
                for ev in cal.date_search(start=search_start, end=search_end, compfilter="VEVENT", expand=False):
                    try:
                        ical_obj = ev.icalendar_instance
                        for component in ical_obj.walk("VEVENT"):
                            if str(component.get("UID", "")) != event_uid:
                                continue

                            if new_summary is not None: component["SUMMARY"] = new_summary
                            if new_start_time is not None:
                                dt = datetime.datetime.fromisoformat(new_start_time)
                                if dt.tzinfo is None: dt = dt.replace(tzinfo=LOCAL_TZ)
                                component["DTSTART"] = icalendar.vDatetime(dt)
                            if new_end_time is not None:
                                dt = datetime.datetime.fromisoformat(new_end_time)
                                if dt.tzinfo is None: dt = dt.replace(tzinfo=LOCAL_TZ)
                                component["DTEND"] = icalendar.vDatetime(dt)
                            if new_description is not None: component["DESCRIPTION"] = new_description
                            if new_location is not None: component["LOCATION"] = new_location

                            ev.delete()
                            cal.save_event(ical_obj.to_ical().decode())
                            return f"Apple Calendar event updated (UID: {event_uid})."
                    except Exception:
                        continue
            except Exception:
                continue
        return f"Apple Calendar event not found (UID: {event_uid})."

    try:
        return _retry(_edit)
    except Exception as e:
        return f"Error editing Apple event: {e}"