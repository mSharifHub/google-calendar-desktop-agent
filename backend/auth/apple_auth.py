"""
Apple Calendar authentication via iCloud CalDAV.

Credentials are stored as a JSON file on disk. An app-specific password
(not the Apple ID password) is required — generate one at
appleid.apple.com → Security → App-Specific Passwords.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

APPLE_CREDS_FILE = "apple_credentials.json"
CALDAV_URL = "https://caldav.icloud.com"


def save_credentials(username: str, app_password: str):
    """Persist Apple ID and app-specific password to disk."""
    with open(APPLE_CREDS_FILE, "w") as f:
        json.dump({"username": username, "app_password": app_password}, f)
    logger.info(f"Apple credentials saved for user: {username}")


def _load_credentials() -> Optional[dict]:
    if os.path.exists(APPLE_CREDS_FILE):
        with open(APPLE_CREDS_FILE) as f:
            return json.load(f)
    return None


def connect_and_verify():
    """
    Connect to iCloud CalDAV and verify credentials.
    Returns an authenticated DAVClient on success.
    Raises ValueError with a descriptive message on any failure.
    """
    logger.info("Connecting to iCloud CalDAV...")
    creds = _load_credentials()
    if not creds:
        raise ValueError("No Apple credentials saved.")

    try:
        import caldav
    except ImportError:
        raise ValueError("The 'caldav' library is not installed. Run: pip install caldav")

    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=creds["username"],
            password=creds["app_password"],
        )
        client.principal()  # Raises on bad credentials or network failure
        logger.info(f"iCloud CalDAV connection verified for {creds['username']}")
        return client
    except Exception as e:
        logger.error(f"iCloud CalDAV connection failed: {e}")
        raise ValueError(f"iCloud CalDAV connection failed: {e}") from e


def get_apple_client():
    """Return an authenticated CalDAV client, or None if not configured or connection fails."""
    try:
        return connect_and_verify()
    except Exception as e:
        logger.error(f"get_apple_client failed: {e}")
        return None


def is_connected() -> bool:
    """Return True if Apple credentials are saved on disk."""
    result = os.path.exists(APPLE_CREDS_FILE)
    logger.debug(f"Apple is_connected={result}")
    return result


def disconnect():
    """Remove saved credentials."""
    if os.path.exists(APPLE_CREDS_FILE):
        os.remove(APPLE_CREDS_FILE)
        logger.info("Apple credentials removed")
