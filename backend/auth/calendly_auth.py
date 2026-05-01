import json
import os
from typing import Optional

CALENDLY_TOKEN_FILE = "calendly_token.json"
CALENDLY_API = "https://api.calendly.com"


def save_token(personal_access_token: str):
    """
    Persist a Calendly Personal Access Token.
    Generate one at: Calendly → Integrations → API & Webhooks → Personal Access Tokens.
    """
    print(f"[AUTH:calendly] save_token() → saving token (length={len(personal_access_token)})")
    with open(CALENDLY_TOKEN_FILE, "w") as f:
        json.dump({"token": personal_access_token}, f)
    print("[AUTH:calendly] save_token() → token saved")


def get_calendly_token() -> Optional[str]:
    print("[AUTH:calendly] get_calendly_token() called")
    if not os.path.exists(CALENDLY_TOKEN_FILE):
        print("[AUTH:calendly] get_calendly_token() → None (no token file)")
        return None
    with open(CALENDLY_TOKEN_FILE) as f:
        data = json.load(f)
    token = data.get("token")
    print(f"[AUTH:calendly] get_calendly_token() → {'token found' if token else 'token missing in file'}")
    return token


def is_connected() -> bool:
    print("[AUTH:calendly] is_connected() called")
    token = get_calendly_token()
    if not token:
        print("[AUTH:calendly] is_connected() → False (no token)")
        return False
    try:
        import requests as http_requests
        print("[AUTH:calendly] is_connected() → verifying token against /users/me")
        resp = http_requests.get(
            f"{CALENDLY_API}/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        result = resp.status_code == 200
        print(f"[AUTH:calendly] is_connected() → HTTP {resp.status_code} → {result}")
        return result
    except Exception as e:
        print(f"[AUTH:calendly] is_connected() → False (error: {e})")
        return False


def disconnect():
    print("[AUTH:calendly] disconnect() called")
    if os.path.exists(CALENDLY_TOKEN_FILE):
        os.remove(CALENDLY_TOKEN_FILE)
        print("[AUTH:calendly] disconnect() → token file removed")
    else:
        print("[AUTH:calendly] disconnect() → token file not found, nothing to remove")
