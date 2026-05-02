"""
Calendly authentication via Personal Access Token.

Generate a token at: Calendly → Integrations → API & Webhooks → Personal Access Tokens.
The token is stored as a JSON file on disk.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

CALENDLY_TOKEN_FILE = "calendly_token.json"
CALENDLY_API = "https://api.calendly.com"


def save_token(personal_access_token: str):
    """Persist a Calendly Personal Access Token to disk."""
    with open(CALENDLY_TOKEN_FILE, "w") as f:
        json.dump({"token": personal_access_token}, f)
    logger.info("Calendly token saved")


def get_calendly_token() -> Optional[str]:
    """Return the stored token, or None if not saved."""
    if not os.path.exists(CALENDLY_TOKEN_FILE):
        logger.debug("Calendly get_token: token file not found")
        return None
    with open(CALENDLY_TOKEN_FILE) as f:
        return json.load(f).get("token")


def is_connected() -> bool:
    """Return True if a Calendly token file exists."""
    result = os.path.exists(CALENDLY_TOKEN_FILE)
    logger.debug(f"Calendly is_connected={result}")
    return result


def disconnect():
    """Remove the saved token."""
    if os.path.exists(CALENDLY_TOKEN_FILE):
        os.remove(CALENDLY_TOKEN_FILE)
        logger.info("Calendly token removed")
