import datetime
import requests as http_requests

from auth.calendly_auth import get_calendly_token, is_connected
from tools.unified_event import UnifiedEvent, _to_utc, _parse_dt
from utils.retry import with_retry

CALENDLY_API = "https://api.calendly.com"
_retry = lambda fn, *a, **kw: with_retry(fn, *a, label="[TOOL:calendly]", **kw)


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_calendly_token()}"}


def fetch_calendly_events(days: int) -> list[UnifiedEvent]:
    if not is_connected(): return []
    try:
        user_uri = \
        _retry(http_requests.get, f"{CALENDLY_API}/users/me", headers=_headers(), timeout=10).json()["resource"]["uri"]
        now = datetime.datetime.now(datetime.timezone.utc)

        resp = _retry(
            http_requests.get,
            f"{CALENDLY_API}/scheduled_events",
            headers=_headers(),
            params={
                "user": user_uri,
                "count": 100,
                "status": "active",
                "min_start_time": now.isoformat(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json().get("collection", [])
    except Exception:
        return []

    out = []
    for e in events:
        out.append(UnifiedEvent(
            id=e.get("uri", "").split("/")[-1],
            title=e.get("name", "Meeting"),
            start=_to_utc(_parse_dt(e["start_time"])),
            end=_to_utc(_parse_dt(e["end_time"])),
            provider="calendly",
        ))
    return out