import requests as http_requests
from langchain_core.tools import tool

CALENDLY_API = "https://api.calendly.com"


def _headers() -> dict:
    print("[TOOL:calendly] _headers() → getting token")
    from auth.calendly_auth import get_calendly_token
    token = get_calendly_token()
    if not token:
        print("[TOOL:calendly] _headers() → RuntimeError: not connected")
        raise RuntimeError(
            "Calendly is not connected. Ask the user to connect their Calendly account "
            "in the Calendar Providers settings."
        )
    print("[TOOL:calendly] _headers() → token acquired")
    return {"Authorization": f"Bearer {token}"}


def _get_user_uri() -> str:
    print("[TOOL:calendly] _get_user_uri() → fetching /users/me")
    resp = http_requests.get(f"{CALENDLY_API}/users/me", headers=_headers(), timeout=10)
    resp.raise_for_status()
    uri = resp.json()["resource"]["uri"]
    print(f"[TOOL:calendly] _get_user_uri() → uri={uri}")
    return uri


@tool
def get_calendly_scheduled_events(count: int = 10) -> str:
    """Get upcoming scheduled meetings from Calendly."""
    print(f"[TOOL:calendly] get_calendly_scheduled_events() called → count={count}")
    try:
        user_uri = _get_user_uri()
        resp = http_requests.get(
            f"{CALENDLY_API}/scheduled_events",
            headers=_headers(),
            params={
                "user": user_uri,
                "count": count,
                "status": "active",
                "sort": "start_time:asc",
            },
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json().get("collection", [])
        print(f"[TOOL:calendly] get_calendly_scheduled_events() → fetched {len(events)} events")
        if not events:
            return "No upcoming Calendly events found."
        lines = []
        for e in events:
            ev_uuid = e.get("uri", "").split("/")[-1]
            lines.append(f"- [ID: {ev_uuid}] {e.get('name', 'Meeting')} at {e.get('start_time', '')}")
        return "\n".join(lines)
    except RuntimeError as e:
        print(f"[TOOL:calendly] get_calendly_scheduled_events() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:calendly] get_calendly_scheduled_events() → error: {e}")
        return f"Error fetching Calendly events: {e}"


@tool
def get_calendly_event_details(event_uuid: str) -> str:
    """Get full details and invitees for a specific Calendly scheduled event by its UUID."""
    print(f"[TOOL:calendly] get_calendly_event_details() called → event_uuid={event_uuid}")
    try:
        resp = http_requests.get(
            f"{CALENDLY_API}/scheduled_events/{event_uuid}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        e = resp.json().get("resource", {})
        print(f"[TOOL:calendly] get_calendly_event_details() → event name={e.get('name')!r}")

        inv_resp = http_requests.get(
            f"{CALENDLY_API}/scheduled_events/{event_uuid}/invitees",
            headers=_headers(),
            timeout=10,
        )
        invitees = [i["email"] for i in inv_resp.json().get("collection", [])]
        print(f"[TOOL:calendly] get_calendly_event_details() → {len(invitees)} invitee(s)")

        return (
            f"Event: {e.get('name')}\n"
            f"Start: {e.get('start_time')}\n"
            f"End:   {e.get('end_time')}\n"
            f"Status: {e.get('status')}\n"
            f"Invitees: {', '.join(invitees) or 'None'}"
        )
    except RuntimeError as e:
        print(f"[TOOL:calendly] get_calendly_event_details() → auth error: {e}")
        return str(e)
    except Exception as e:
        print(f"[TOOL:calendly] get_calendly_event_details() → error: {e}")
        return f"Error fetching Calendly event details: {e}"
