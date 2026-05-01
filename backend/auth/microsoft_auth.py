import json
import os
import time
from typing import Optional
from urllib.parse import urlencode

import requests as http_requests

OUTLOOK_CREDS_FILE = "outlook_credentials.json"
OUTLOOK_TOKEN_FILE = "outlook_token.json"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
REDIRECT_URI = "http://localhost:8000/auth/outlook/callback"
SCOPES = "Calendars.ReadWrite User.Read offline_access"


def _load_creds() -> Optional[dict]:
    if os.path.exists(OUTLOOK_CREDS_FILE):
        with open(OUTLOOK_CREDS_FILE) as f:
            return json.load(f)
    return None


def _load_token() -> Optional[dict]:
    if os.path.exists(OUTLOOK_TOKEN_FILE):
        with open(OUTLOOK_TOKEN_FILE) as f:
            return json.load(f)
    return None


def _save_token(token: dict):
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    with open(OUTLOOK_TOKEN_FILE, "w") as f:
        json.dump(token, f)
    print(f"[AUTH:outlook] token saved (expires_in={token.get('expires_in')}s)")


def save_app_credentials(client_id: str, client_secret: str, tenant_id: str = "common"):
    """Persist the Azure app registration credentials."""
    print(f"[AUTH:outlook] save_app_credentials() → client_id={client_id[:8]}..., tenant_id={tenant_id}")
    with open(OUTLOOK_CREDS_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret, "tenant_id": tenant_id}, f)
    print("[AUTH:outlook] app credentials saved")


def get_auth_url() -> str:
    """Return the Microsoft OAuth2 authorization URL for the user to visit."""
    print("[AUTH:outlook] get_auth_url() called")
    creds = _load_creds()
    if not creds:
        print("[AUTH:outlook] get_auth_url() → ValueError: no app credentials")
        raise ValueError("Outlook app credentials not configured. Provide client_id and client_secret first.")
    tenant = creds.get("tenant_id", "common")
    params = urlencode({
        "client_id": creds["client_id"],
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_mode": "query",
    })
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{params}"
    print(f"[AUTH:outlook] get_auth_url() → auth URL generated (tenant={tenant})")
    return url


def exchange_code(code: str):
    """Exchange an authorization code for an access/refresh token pair."""
    print(f"[AUTH:outlook] exchange_code() called (code length={len(code)})")
    creds = _load_creds()
    if not creds:
        print("[AUTH:outlook] exchange_code() → ValueError: no app credentials")
        raise ValueError("Outlook app credentials not configured.")
    tenant = creds.get("tenant_id", "common")
    print(f"[AUTH:outlook] exchange_code() → POSTing to Microsoft token endpoint (tenant={tenant})")
    resp = http_requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        },
        timeout=15,
    )
    print(f"[AUTH:outlook] exchange_code() → HTTP {resp.status_code}")
    resp.raise_for_status()
    _save_token(resp.json())
    print("[AUTH:outlook] exchange_code() → token exchanged and saved")


def get_access_token() -> Optional[str]:
    """Return a valid access token, refreshing automatically if expired."""
    print("[AUTH:outlook] get_access_token() called")
    token = _load_token()
    if not token:
        print("[AUTH:outlook] get_access_token() → None (no token file)")
        return None

    # Still valid (60-second buffer)
    if token.get("expires_at", 0) > time.time() + 60:
        print("[AUTH:outlook] get_access_token() → returning cached token (still valid)")
        return token.get("access_token")

    # Attempt refresh
    print("[AUTH:outlook] get_access_token() → token expired, attempting refresh")
    creds = _load_creds()
    if not creds or not token.get("refresh_token"):
        print("[AUTH:outlook] get_access_token() → None (no creds or no refresh_token)")
        return None

    tenant = creds.get("tenant_id", "common")
    resp = http_requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
            "scope": SCOPES,
        },
        timeout=15,
    )
    print(f"[AUTH:outlook] get_access_token() refresh → HTTP {resp.status_code}")
    if resp.status_code != 200:
        print("[AUTH:outlook] get_access_token() → None (refresh failed)")
        return None
    new_token = resp.json()
    _save_token(new_token)
    print("[AUTH:outlook] get_access_token() → token refreshed successfully")
    return new_token.get("access_token")


def is_connected() -> bool:
    print("[AUTH:outlook] is_connected() called")
    result = get_access_token() is not None
    print(f"[AUTH:outlook] is_connected() → {result}")
    return result


def disconnect():
    print("[AUTH:outlook] disconnect() called")
    for f in [OUTLOOK_CREDS_FILE, OUTLOOK_TOKEN_FILE]:
        if os.path.exists(f):
            os.remove(f)
            print(f"[AUTH:outlook] disconnect() → removed {f}")
        else:
            print(f"[AUTH:outlook] disconnect() → {f} not found, skipping")
