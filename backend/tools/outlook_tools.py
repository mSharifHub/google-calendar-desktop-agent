import datetime
import logging
from typing import Optional
import requests as http_requests

from auth.microsoft_auth import get_access_token, is_connected
from tools.unified_event import UnifiedEvent, _to_utc, _parse_dt
from utils.retry import with_retry

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LOCAL_TZ = "America/Los_Angeles"

_retry = lambda fn, *a, **kw: with_retry(fn, *a, label="[TOOL:outlook]", **kw)


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"}


def fetch_outlook_events(days: int) -> list[UnifiedEvent]:
    if not is_connected(): return []
    logger.info(f"Fetching Outlook events for next {days} days")
    now = datetime.datetime.now(datetime.timezone.utc)
    end = now + datetime.timedelta(days=days)

    try:
        resp = _retry(
            http_requests.get,
            f"{GRAPH_BASE}/me/calendarView",
            headers=_headers(),
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
        events = resp.json().get("value", [])
    except Exception as e:
        logger.error(f"fetch_outlook_events failed: {e}")
        return []

    logger.debug(f"Outlook returned {len(events)} events")
    out = []
    for e in events:
        out.append(UnifiedEvent(
            id=e.get("id", ""),
            title=e.get("subject", "No title"),
            start=_to_utc(_parse_dt(e["start"]["dateTime"])),
            end=_to_utc(_parse_dt(e["end"]["dateTime"])),
            provider="outlook",
            location=e.get("location", {}).get("displayName", ""),
            description=e.get("bodyPreview", ""),
        ))
    return out


def create_outlook_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
) -> str:
    logger.info(f"Creating Outlook event: '{summary}' from {start_time} to {end_time}")
    if not is_connected(): return "Auth Error: Outlook not connected."
    body: dict = {
        "subject": summary,
        "start": {"dateTime": start_time, "timeZone": LOCAL_TZ},
        "end": {"dateTime": end_time, "timeZone": LOCAL_TZ},
    }
    if description: body["body"] = {"contentType": "text", "content": description}
    if location: body["location"] = {"displayName": location}

    _retry(http_requests.post, f"{GRAPH_BASE}/me/events", headers=_headers(), json=body, timeout=15)
    return f"Outlook event created: '{summary}'"


def delete_outlook_event(event_id: str) -> str:
    logger.info(f"Deleting Outlook event: {event_id}")
    if not is_connected(): return "Auth Error: Outlook not connected."
    _retry(http_requests.delete, f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(), timeout=15)
    logger.info(f"Outlook event deleted: {event_id}")
    return f"Outlook event deleted successfully (ID: {event_id})."


def edit_outlook_event(
        event_id: str,
        new_summary: Optional[str] = None,
        new_start_time: Optional[str] = None,
        new_end_time: Optional[str] = None,
        new_description: Optional[str] = None,
        new_location: Optional[str] = None,
) -> str:
    logger.info(f"Editing Outlook event: {event_id}")
    if not is_connected(): return "Auth Error: Outlook not connected."
    patch: dict = {}
    if new_summary is not None: patch["subject"] = new_summary
    if new_start_time is not None: patch["start"] = {"dateTime": new_start_time, "timeZone": LOCAL_TZ}
    if new_end_time is not None: patch["end"] = {"dateTime": new_end_time, "timeZone": LOCAL_TZ}
    if new_description is not None: patch["body"] = {"contentType": "text", "content": new_description}
    if new_location is not None: patch["location"] = {"displayName": new_location}

    logger.debug(f"Outlook patch fields: {list(patch.keys())}")
    _retry(http_requests.patch, f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(), json=patch, timeout=15)
    logger.info(f"Outlook event updated: {event_id}")
    return "Outlook event updated successfully."