"""
Calendly authentication via Personal Access Token.

Generate a token at: Calendly → Integrations → API & Webhooks → Personal Access Tokens.
The token is stored as a JSON file on disk.
"""
import json
import os
from typing import Optional

CALENDLY_TOKEN_FILE = "calendly_token.json"
CALENDLY_API = "https://api.calendly.com"


def save_token(personal_access_token: str):
    """Persist a Calendly Personal Access Token to disk."""
    with open(CALENDLY_TOKEN_FILE, "w") as f:
        json.dump({"token": personal_access_token}, f)


def get_calendly_token() -> Optional[str]:
    """Return the stored token, or None if not saved."""
    if not os.path.exists(CALENDLY_TOKEN_FILE):
        return None
    with open(CALENDLY_TOKEN_FILE) as f:
        return json.load(f).get("token")


def is_connected() -> bool:
    """Return True if a Calendly token file exists."""
    return os.path.exists(CALENDLY_TOKEN_FILE)


def disconnect():
    """Remove the saved token."""
    if os.path.exists(CALENDLY_TOKEN_FILE):
        os.remove(CALENDLY_TOKEN_FILE)
