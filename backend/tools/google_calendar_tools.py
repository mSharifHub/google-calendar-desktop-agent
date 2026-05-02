import datetime
import logging
from typing import Optional

from auth.google_auth import get_service, is_connected
from tools.unified_event import UnifiedEvent, _to_utc, _parse_dt
from utils.retry import with_retry

logger = logging.getLogger(__name__)

_retry = lambda fn, *a, **kw: with_retry(fn, *a, label="[TOOL:google]", **kw)


def fetch_google_events(days: int) -> list[UnifiedEvent]:
    """Fetch Google Calendar events as UnifiedEvent objects."""
    if not is_connected():
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=days)

    try:
        service = _retry(get_service, 'calendar', 'v3')
        req = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=100,
            singleEvents=True,
            orderBy='startTime',
        )
        events = _retry(req.execute).get('items', [])
    except Exception as e:
        logger.error(f"Error fetching Google events: {e}")
        return []

    out = []
    for e in events:
        is_all_day = 'date' in e['start']
        s = e['start'].get('dateTime', e['start'].get('date', ''))
        en = e['end'].get('dateTime', e['end'].get('date', ''))
        out.append(UnifiedEvent(
            id=e.get('id', ''),
            title=e.get('summary', 'No title'),
            start=_to_utc(_parse_dt(s)),
            end=_to_utc(_parse_dt(en)),
            provider='google',
            location=e.get('location', ''),
            description=e.get('description', ''),
            is_all_day=is_all_day
        ))
    return out


def create_google_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
) -> str:
    if not is_connected(): return "Auth Error: Google Calendar not connected."
    service = _retry(get_service, 'calendar', 'v3')
    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'America/Los_Angeles'},
        'end': {'dateTime': end_time, 'timeZone': 'America/Los_Angeles'},
    }
    if description: event['description'] = description
    if location: event['location'] = location

    event_result = _retry(service.events().insert(calendarId='primary', body=event).execute)
    return f"Event created successfully: {summary}. Link: {event_result.get('htmlLink')}"


def delete_google_event(event_id: str) -> str:
    if not is_connected(): return "Auth Error: Google Calendar not connected."
    service = _retry(get_service, 'calendar', 'v3')
    _retry(service.events().delete(calendarId='primary', eventId=event_id).execute)
    return f"Google Calendar event deleted successfully (ID: {event_id})."


def edit_google_event(
        event_id: str,
        new_summary: Optional[str] = None,
        new_start_time: Optional[str] = None,
        new_end_time: Optional[str] = None,
        new_description: Optional[str] = None,
        new_location: Optional[str] = None,
) -> str:
    if not is_connected(): return "Auth Error: Google Calendar not connected."
    service = _retry(get_service, 'calendar', 'v3')
    body = _retry(service.events().get(calendarId='primary', eventId=event_id).execute)

    if new_summary is not None: body['summary'] = new_summary
    if new_description is not None: body['description'] = new_description
    if new_location is not None: body['location'] = new_location
    if new_start_time is not None: body['start']['dateTime'] = new_start_time
    if new_end_time is not None: body['end']['dateTime'] = new_end_time

    _retry(service.events().update(calendarId='primary', eventId=event_id, body=body).execute)
    return f"Event updated successfully."