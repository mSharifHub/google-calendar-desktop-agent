import datetime
from typing import Optional

import requests as http_requests
from langchain_core.tools import tool

from auth.microsoft_auth import get_access_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LOCAL_TZ = "America/Los_Angeles"


def _headers() -> dict:
    print("[TOOL:outlook] _headers() → getting access token")
    token = get_access_token()
    if not token:
        print("[TOOL:outlook] _headers() → RuntimeError: not connected")
        raise RuntimeError(
            "Outlook is not connected. Ask the user to connect their Outlook account "
            "in the Calendar Providers settings."
        )
    print("[TOOL:outlook] _headers() → token acquired")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@tool
def get_outlook_upcoming_events(max_results: int = 10) -> str:
    """Get upcoming events from Outlook / Microsoft 365 Calendar."""
    print(f"[TOOL:outlook] get_outlook_upcoming_events() called → max_results={max_results}")
    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=30)
    try:
        resp = http_requests.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers=_headers(),
            params={
                "startDateTime": now.isoformat().replace("+00:00", "Z"),
                "endDateTime": end.isoformat().replace("+00:00", "Z"),
                "$top": max_results,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except RuntimeError as e:
        print(f"[TOOL:outlook] get_outlook_upcoming_events() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:outlook] get_outlook_upcoming_events() → API error: {e}")
        return f"Error fetching Outlook events: {e}"

    events = resp.json().get("value", [])
    print(f"[TOOL:outlook] get_outlook_upcoming_events() → fetched {len(events)} events")
    if not events:
        return "No upcoming Outlook events found."
    lines = [
        f"- [ID: {e['id']}] {e.get('subject', 'No title')} at {e['start']['dateTime']}"
        for e in events
    ]
    return "\n".join(lines)


@tool
def get_outlook_todays_events() -> str:
    """Get today's events from Outlook / Microsoft 365 Calendar."""
    print("[TOOL:outlook] get_outlook_todays_events() called")
    local_tz = datetime.timezone(datetime.timedelta(hours=-7))
    today = datetime.datetime.now(local_tz).date()
    start = datetime.datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=local_tz)
    end = datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=local_tz)
    print(f"[TOOL:outlook] get_outlook_todays_events() → querying for {today}")
    try:
        resp = http_requests.get(
            f"{GRAPH_BASE}/me/calendarView",
            headers=_headers(),
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$top": 20,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except RuntimeError as e:
        print(f"[TOOL:outlook] get_outlook_todays_events() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:outlook] get_outlook_todays_events() → API error: {e}")
        return f"Error fetching Outlook events: {e}"

    events = resp.json().get("value", [])
    print(f"[TOOL:outlook] get_outlook_todays_events() → fetched {len(events)} events for {today}")
    if not events:
        return f"No Outlook events for today ({today})."
    lines = [
        f"- [ID: {e['id']}] {e.get('subject', 'No title')} at {e['start']['dateTime']}"
        for e in events
    ]
    return "\n".join(lines)


@tool
def create_outlook_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Create a new event in Outlook / Microsoft 365 Calendar.
    start_time and end_time must be ISO 8601 strings (e.g. '2026-04-28T14:30:00').
    """
    print(f"[TOOL:outlook] create_outlook_event() called → summary={summary!r}, start={start_time}, end={end_time}")
    body: dict = {
        "subject": summary,
        "start": {"dateTime": start_time, "timeZone": LOCAL_TZ},
        "end": {"dateTime": end_time, "timeZone": LOCAL_TZ},
    }
    if description:
        body["body"] = {"contentType": "text", "content": description}
    if location:
        body["location"] = {"displayName": location}
    try:
        resp = http_requests.post(
            f"{GRAPH_BASE}/me/events", headers=_headers(), json=body, timeout=15
        )
        resp.raise_for_status()
        event = resp.json()
        print(f"[TOOL:outlook] create_outlook_event() → created id={event.get('id', '')[:20]}...")
        return f"Outlook event created: '{summary}' (ID: {event.get('id', '')})"
    except RuntimeError as e:
        print(f"[TOOL:outlook] create_outlook_event() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:outlook] create_outlook_event() → API error: {e}")
        return f"Error creating Outlook event: {e}"


@tool
def delete_outlook_event(event_id: str) -> str:
    """Delete an Outlook / Microsoft 365 Calendar event by its ID."""
    print(f"[TOOL:outlook] delete_outlook_event() called → event_id={event_id[:20]}...")
    try:
        resp = http_requests.delete(
            f"{GRAPH_BASE}/me/events/{event_id}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        print(f"[TOOL:outlook] delete_outlook_event() → deleted successfully")
        return f"Outlook event deleted successfully (ID: {event_id})."
    except RuntimeError as e:
        print(f"[TOOL:outlook] delete_outlook_event() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:outlook] delete_outlook_event() → error: {e}")
        return f"Error deleting Outlook event: {e}"


@tool
def edit_outlook_event(
    event_id: str,
    new_summary: Optional[str] = None,
    new_start_time: Optional[str] = None,
    new_end_time: Optional[str] = None,
    new_description: Optional[str] = None,
    new_location: Optional[str] = None,
) -> str:
    """
    Edit an existing Outlook Calendar event by its ID.
    Only provided fields are updated; omit fields to leave them unchanged.
    """
    print(f"[TOOL:outlook] edit_outlook_event() called → event_id={event_id[:20]}...")
    patch: dict = {}
    if new_summary is not None:
        patch["subject"] = new_summary
    if new_start_time is not None:
        patch["start"] = {"dateTime": new_start_time, "timeZone": LOCAL_TZ}
    if new_end_time is not None:
        patch["end"] = {"dateTime": new_end_time, "timeZone": LOCAL_TZ}
    if new_description is not None:
        patch["body"] = {"contentType": "text", "content": new_description}
    if new_location is not None:
        patch["location"] = {"displayName": new_location}
    print(f"[TOOL:outlook] edit_outlook_event() → patching fields: {list(patch.keys())}")
    try:
        resp = http_requests.patch(
            f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(), json=patch, timeout=15
        )
        resp.raise_for_status()
        print("[TOOL:outlook] edit_outlook_event() → update successful")
        return "Outlook event updated successfully."
    except RuntimeError as e:
        print(f"[TOOL:outlook] edit_outlook_event() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:outlook] edit_outlook_event() → API error: {e}")
        return f"Error updating Outlook event: {e}"
