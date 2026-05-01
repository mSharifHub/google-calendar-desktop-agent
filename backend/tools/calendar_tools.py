import datetime
from langchain_core.tools import tool
from auth.google_auth import get_service


@tool
def create_event(summary: str, start_time: str, end_time: str, description: str = None, location: str = None, url: str = None) -> str:
    """
    Creates a new event in the Google Calendar.
    start_time and end_time MUST be ISO 8601 formatted strings without timezone offsets (e.g., '2026-04-28T14:30:00').
    description: optional event description or notes.
    location: optional physical or virtual location.
    url: optional link to attach to the event (added to description).
    """
    print(f"[TOOL:google] create_event() called → summary={summary!r}, start={start_time}, end={end_time}")
    try:
        service = get_service('calendar', 'v3')
    except Exception as e:
        print(f"[TOOL:google] create_event() → auth error: {e}")
        return f"Google Calendar is not connected: {e}"

    full_description = description or ''
    if url:
        full_description = f"{full_description}\n{url}".strip()

    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'America/Los_Angeles'},
        'end': {'dateTime': end_time, 'timeZone': 'America/Los_Angeles'},
    }

    if full_description:
        event['description'] = full_description
    if location:
        event['location'] = location

    try:
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        print(f"[TOOL:google] create_event() → created event id={event_result.get('id')}")
        return f"Event created successfully: {summary}. Link: {event_result.get('htmlLink')}"
    except Exception as e:
        print(f"[TOOL:google] create_event() → error: {e}")
        return f"Error creating event: {e}"


@tool
def get_upcoming_events(max_results: int = 10) -> str:
    """Get the user's upcoming Google Calendar events. Returns the event name and start time."""
    print(f"[TOOL:google] get_upcoming_events() called → max_results={max_results}")
    try:
        service = get_service('calendar', 'v3')
    except Exception as e:
        print(f"[TOOL:google] get_upcoming_events() → auth error: {e}")
        return f"Google Calendar is not connected: {e}"

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', '') + 'Z'

    try:
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime').execute()
    except Exception as e:
        print(f"[TOOL:google] get_upcoming_events() → API error: {e}")
        return f"Error fetching Google Calendar events: {e}"

    events = events_result.get('items', [])
    print(f"[TOOL:google] get_upcoming_events() → fetched {len(events)} events")

    event_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'No title')
        event_id = event.get('id')
        event_list.append(f"- [ID: {event_id}] {summary} at {start}")

    return '\n'.join(event_list) or 'No upcoming events found.'


@tool
def get_todays_events() -> str:
    """Get the user's Google Calendar events for today only (midnight to midnight local time)."""
    print("[TOOL:google] get_todays_events() called")
    try:
        service = get_service('calendar', 'v3')
    except Exception as e:
        print(f"[TOOL:google] get_todays_events() → auth error: {e}")
        return f"Google Calendar is not connected: {e}"

    local_tz = datetime.timezone(datetime.timedelta(hours=-7))  # America/Los_Angeles (PDT)
    today = datetime.datetime.now(local_tz).date()
    time_min = datetime.datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=local_tz).isoformat()
    time_max = datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=local_tz).isoformat()
    print(f"[TOOL:google] get_todays_events() → querying for {today}")

    try:
        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            maxResults=20, singleEvents=True,
            orderBy='startTime').execute()
    except Exception as e:
        print(f"[TOOL:google] get_todays_events() → API error: {e}")
        return f"Error fetching Google Calendar events: {e}"

    events = events_result.get('items', [])
    print(f"[TOOL:google] get_todays_events() → fetched {len(events)} events for {today}")

    event_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'No title')
        event_id = event.get('id')
        event_list.append(f"- [ID: {event_id}] {summary} at {start}")

    return '\n'.join(event_list) or f'No events found for today ({today}).'


@tool
def delete_google_event(event_id: str) -> str:
    """Delete a Google Calendar event by its ID."""
    print(f"[TOOL:google] delete_google_event() called → event_id={event_id}")
    try:
        service = get_service('calendar', 'v3')
    except Exception as e:
        print(f"[TOOL:google] delete_google_event() → auth error: {e}")
        return f"Google Calendar is not connected: {e}"
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f"[TOOL:google] delete_google_event() → deleted event_id={event_id}")
        return f"Google Calendar event deleted successfully (ID: {event_id})."
    except Exception as e:
        print(f"[TOOL:google] delete_google_event() → error: {e}")
        return f"Error deleting Google Calendar event: {e}"


@tool
def edit_event(event_id: str, new_summary: str = None, new_start_time: str = None, new_end_time: str = None, new_description: str = None, new_location: str = None) -> str:
    """
    Edit an existing Google Calendar event by its ID.
    Only the provided fields will be updated; omitted fields remain unchanged.
    new_start_time and new_end_time must be ISO 8601 strings (e.g. '2026-04-28T14:30:00').
    """
    print(f"[TOOL:google] edit_event() called → event_id={event_id}")
    try:
        service = get_service('calendar', 'v3')
    except Exception as e:
        print(f"[TOOL:google] edit_event() → auth error: {e}")
        return f"Google Calendar is not connected: {e}"

    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        print(f"[TOOL:google] edit_event() → fetched event: {event.get('summary')!r}")
    except Exception as e:
        print(f"[TOOL:google] edit_event() → error fetching event: {e}")
        return f"Error fetching event: {e}"

    if new_summary is not None:
        event['summary'] = new_summary
    if new_description is not None:
        event['description'] = new_description
    if new_location is not None:
        event['location'] = new_location
    if new_start_time is not None:
        event['start'] = {'dateTime': new_start_time, 'timeZone': 'America/Los_Angeles'}
    if new_end_time is not None:
        event['end'] = {'dateTime': new_end_time, 'timeZone': 'America/Los_Angeles'}

    try:
        updated = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        print(f"[TOOL:google] edit_event() → updated event: {updated.get('summary')!r}")
        return f"Event updated successfully: {updated.get('summary')}. Link: {updated.get('htmlLink')}"
    except Exception as e:
        print(f"[TOOL:google] edit_event() → error updating event: {e}")
        return f"Error updating event: {e}"
