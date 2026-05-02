import importlib
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from auth.google_auth import connect as google_connect_auth, disconnect as google_disconnect_auth
from auth.microsoft_auth import save_app_credentials, get_auth_url, exchange_code, disconnect as microsoft_disconnect_auth
from auth.apple_auth import save_credentials as apple_save_credentials, connect_and_verify as apple_connect_and_verify, disconnect as apple_disconnect_auth
from auth.calendly_auth import save_token as calendly_save_token, is_connected as is_calendly_connected, disconnect as calendly_disconnect_auth
from tools.unified_calendar_tool import get_all_events, find_conflicts


_CALENDAR_PROVIDER_MODULES: dict[str, str] = {
    "google": "auth.google_auth",
    "outlook": "auth.microsoft_auth",
    "apple": "auth.apple_auth",
    "calendly": "auth.calendly_auth",
}


def _provider_connected(auth_module: str) -> bool:
    try:
        return importlib.import_module(auth_module).is_connected()
    except Exception:
        return False


# ---------- Request models ----------

class OutlookSetupRequest(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: Optional[str] = "common"


class AppleConnectRequest(BaseModel):
    username: str
    app_password: str


class CalendlyConnectRequest(BaseModel):
    token: str


# ---------- Router ----------

router = APIRouter()


@router.get("/calendars/status")
def calendars_status():
    return {name: _provider_connected(mod) for name, mod in _CALENDAR_PROVIDER_MODULES.items()}


# --- Provider-specific auth ---

@router.post("/auth/google/connect")
async def google_connect():
    def do_connect():
        google_connect_auth()

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, do_connect)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}


@router.post("/auth/outlook/setup")
def outlook_setup(req: OutlookSetupRequest):
    try:
        save_app_credentials(req.client_id, req.client_secret, req.tenant_id or "common")
        return {"auth_url": get_auth_url()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/auth/outlook/callback")
def outlook_callback(
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if error:
        return HTMLResponse(
            content=f"""
            <html><body style="font-family:sans-serif;text-align:center;padding:60px">
              <h2 style="color:#dc2626">Authentication Failed</h2>
              <p>{error}</p>
              <p>You can close this tab.</p>
            </body></html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received.")

    try:
        exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return HTMLResponse(content="""
    <html><body style="font-family:sans-serif;text-align:center;padding:60px">
      <h2 style="color:#16a34a">&#10003; Outlook Connected!</h2>
      <p>Your Microsoft Calendar has been linked successfully.</p>
      <p style="color:#6b7280">You can close this tab and return to the app.</p>
      <script>setTimeout(() => window.close(), 2000);</script>
    </body></html>
    """)


@router.post("/auth/apple/connect")
def apple_connect(req: AppleConnectRequest):
    apple_save_credentials(req.username, req.app_password)
    try:
        apple_connect_and_verify()
    except Exception as e:
        apple_disconnect_auth()
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.post("/auth/calendly/connect")
def calendly_connect(req: CalendlyConnectRequest):
    try:
        calendly_save_token(req.token)
        if not is_calendly_connected():
            calendly_disconnect_auth()
            raise HTTPException(
                status_code=400,
                detail="Token verification failed. Check your Calendly Personal Access Token.",
            )
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/{provider}/disconnect")
def disconnect(provider: str):
    disconnect_actions = {
        "google": google_disconnect_auth,
        "outlook": microsoft_disconnect_auth,
        "apple": apple_disconnect_auth,
        "calendly": calendly_disconnect_auth,
    }
    action = disconnect_actions.get(provider)
    if not action:
        raise HTTPException(status_code=404, detail="Provider not found.")
    action()
    return {"status": "ok"}


# --- Unified calendar actions ---

@router.get("/calendars/sync")
def calendars_sync(days_ahead: int = Query(default=7)):
    try:
        events = get_all_events(days_ahead)
        return {
            "days_ahead": days_ahead,
            "count": len(events),
            "events": [
                {
                    "id": e.id,
                    "title": e.title,
                    "start": e.start.isoformat(),
                    "end": e.end.isoformat(),
                    "provider": e.provider,
                    "location": e.location,
                    "description": e.description,
                    "is_all_day": e.is_all_day,
                }
                for e in events
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendars/conflicts")
def calendars_conflicts(days_ahead: int = Query(default=7)):
    try:
        events = get_all_events(days_ahead)
        conflicts = find_conflicts(events)
        return {
            "days_ahead": days_ahead,
            "conflict_count": len(conflicts),
            "conflicts": [
                {
                    "event_a": {"id": a.id, "title": a.title, "start": a.start.isoformat(), "end": a.end.isoformat(), "provider": a.provider},
                    "event_b": {"id": b.id, "title": b.title, "start": b.start.isoformat(), "end": b.end.isoformat(), "provider": b.provider},
                }
                for a, b in conflicts
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))