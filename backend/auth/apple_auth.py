import json
import os
from typing import Optional

APPLE_CREDS_FILE = "apple_credentials.json"
CALDAV_URL = "https://caldav.icloud.com"


def save_credentials(username: str, app_password: str):
    """
    Persist Apple ID and an app-specific password.
    Generate the app-specific password at appleid.apple.com → Security → App-Specific Passwords.
    """
    print(f"[AUTH:apple] save_credentials() → username={username}")
    with open(APPLE_CREDS_FILE, "w") as f:
        json.dump({"username": username, "app_password": app_password}, f)
    print("[AUTH:apple] save_credentials() → credentials saved")


def _load_credentials() -> Optional[dict]:
    if os.path.exists(APPLE_CREDS_FILE):
        with open(APPLE_CREDS_FILE) as f:
            return json.load(f)
    return None


def connect_and_verify():
    """
    Connect to iCloud CalDAV and verify credentials.
    Raises a descriptive ValueError on any failure so the caller can surface the real error.
    """
    print("[AUTH:apple] connect_and_verify() called")
    creds = _load_credentials()
    if not creds:
        print("[AUTH:apple] connect_and_verify() → ValueError: no credentials saved")
        raise ValueError("No Apple credentials saved.")

    try:
        import caldav
    except ImportError:
        print("[AUTH:apple] connect_and_verify() → ValueError: caldav library not installed")
        raise ValueError("The 'caldav' library is not installed. Run: pip install caldav")

    print(f"[AUTH:apple] connect_and_verify() → connecting to {CALDAV_URL} as {creds['username']}")
    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=creds["username"],
            password=creds["app_password"],
        )
        client.principal()  # Raises AuthorizationError on bad credentials, DAVError on network issues
        print("[AUTH:apple] connect_and_verify() → connection verified successfully")
        return client
    except Exception as e:
        # Surface the original exception message so the user knows what went wrong
        print(f"[AUTH:apple] connect_and_verify() → ValueError: {e}")
        raise ValueError(f"iCloud CalDAV connection failed: {e}") from e


def get_apple_client():
    """Return an authenticated CalDAV client or None if not configured / connection fails."""
    print("[AUTH:apple] get_apple_client() called")
    try:
        client = connect_and_verify()
        print("[AUTH:apple] get_apple_client() → client returned")
        return client
    except Exception as e:
        print(f"[AUTH:apple] get_apple_client() → None (error: {e})")
        return None


def is_connected() -> bool:
    print("[AUTH:apple] is_connected() called")
    if not os.path.exists(APPLE_CREDS_FILE):
        print("[AUTH:apple] is_connected() → False (no credentials file)")
        return False
    result = get_apple_client() is not None
    print(f"[AUTH:apple] is_connected() → {result}")
    return result


def disconnect():
    print("[AUTH:apple] disconnect() called")
    if os.path.exists(APPLE_CREDS_FILE):
        os.remove(APPLE_CREDS_FILE)
        print("[AUTH:apple] disconnect() → credentials file removed")
    else:
        print("[AUTH:apple] disconnect() → credentials file not found, nothing to remove")
