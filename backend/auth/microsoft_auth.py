"""
Outlook / Microsoft 365 authentication via OAuth2.

Flow:
  1. Call save_app_credentials() with Azure app registration details.
  2. Call get_auth_url() and direct the user to the returned URL.
  3. Microsoft redirects to /auth/outlook/callback with a code; call exchange_code(code).
  4. get_access_token() returns a valid token, auto-refreshing when needed.
"""
import json
import os
import time
from typing import Optional
from urllib.parse import urlencode

import requests as http_requests

OUTLOOK_CREDS_FILE = "outlook_credentials.json"
OUTLOOK_TOKEN_FILE = "outlook_token.json"

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


def save_app_credentials(client_id: str, client_secret: str, tenant_id: str = "common"):
    """Persist Azure app registration credentials to disk."""
    with open(OUTLOOK_CREDS_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret, "tenant_id": tenant_id}, f)


def get_auth_url() -> str:
    """Return the Microsoft OAuth2 authorization URL for the user to visit."""
    creds = _load_creds()
    if not creds:
        raise ValueError("Outlook app credentials not configured. Provide client_id and client_secret first.")
    tenant = creds.get("tenant_id", "common")
    params = urlencode({
        "client_id": creds["client_id"],
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_mode": "query",
    })
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{params}"


def exchange_code(code: str):
    """Exchange an authorization code for an access/refresh token pair."""
    creds = _load_creds()
    if not creds:
        raise ValueError("Outlook app credentials not configured.")
    tenant = creds.get("tenant_id", "common")
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
    resp.raise_for_status()
    _save_token(resp.json())


def get_access_token() -> Optional[str]:
    """
    Return a valid access token, refreshing automatically when near expiry.
    Returns None if no token is saved or refresh fails.
    """
    token = _load_token()
    if not token:
        return None

    # Still valid with a 60-second buffer
    if token.get("expires_at", 0) > time.time() + 60:
        return token.get("access_token")

    # Attempt token refresh
    creds = _load_creds()
    if not creds or not token.get("refresh_token"):
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
    if resp.status_code != 200:
        print(f"[AUTH:outlook] token refresh failed (HTTP {resp.status_code})")
        return None
    new_token = resp.json()
    _save_token(new_token)
    return new_token.get("access_token")


def is_connected() -> bool:
    """Return True if an Outlook token file exists."""
    return os.path.exists(OUTLOOK_TOKEN_FILE)


def disconnect():
    """Remove saved credentials and token."""
    for f in [OUTLOOK_CREDS_FILE, OUTLOOK_TOKEN_FILE]:
        if os.path.exists(f):
            os.remove(f)
