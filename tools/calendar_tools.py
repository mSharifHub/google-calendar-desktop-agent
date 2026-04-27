import datetime
from langchain_core.tools import tool
from auth.google_auth import authenticate_google_calendar


@tool
def create_event(summary: str, start_time: str, end_time: str, description: str = None, location: str = None, url: str = None) -> str:
    """
    Creates a new event in the Google Calendar.
    start_time and end_time MUST be ISO 8601 formatted strings without timezone offsets (e.g., '2026-04-28T14:30:00').
    description: optional event description or notes.
    location: optional physical or virtual location.
    url: optional link to attach to the event (added to description).
    """
    service = authenticate_google_calendar()

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
        return f"Event created successfully: {summary}. Link: {event_result.get('htmlLink')}"
    except Exception as e:
        return f"Error creating event: {e}"



@tool
def get_upcoming_events(max_results: int = 10) -> str:
    """Get the user's upcoming Google Calendar events. Returns the event name and start time."""
    service = authenticate_google_calendar()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', '') + 'Z'

    events_result = service.events().list(
        calendarId='primary', timeMin=now,
        maxResults=max_results, singleEvents=True,
        orderBy='startTime').execute()

    events = events_result.get('items', [])

    event_list = []

    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'No title')
        event_list.append(f"{summary} — {start}")

    return '\n'.join(event_list) or 'No upcoming events found.'









tools = [create_event,get_upcoming_events]
