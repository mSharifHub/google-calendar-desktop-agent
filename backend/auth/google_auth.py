"""
Google Calendar authentication via OAuth2.

Requires credentials.json (downloaded from Google Cloud Console) in the working directory.
The user token is cached in token.json after the first login.
"""
import logging
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://mail.google.com/',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

TOKEN_FILE = 'token.json'


def is_connected() -> bool:
    """Return True if a valid (or refreshable) Google token exists — no OAuth flow triggered."""
    if not os.path.exists(TOKEN_FILE):
        logger.debug("Google is_connected=False (token.json not found)")
        return False
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        result = creds.valid or (creds.expired and bool(creds.refresh_token))
        logger.debug(f"Google is_connected={result} (valid={creds.valid}, expired={creds.expired})")
        return result
    except Exception as e:
        logger.warning(f"Google is_connected check failed: {e}")
        return False


def connect():
    """
    Run the full OAuth2 flow (opens a browser) and save the token.
    Blocking — intended to be called inside run_in_executor.
    """
    logger.info("Starting Google OAuth2 flow")
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())
    logger.info("Google OAuth2 flow complete, token saved")
    return creds


def disconnect():
    """Remove the cached token, effectively disconnecting Google Calendar."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        logger.info("Google token removed")


def get_google_creds():
    """
    Return valid Google credentials, refreshing automatically if expired.
    Raises RuntimeError if the user has not connected Google Calendar yet.
    """
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            "Google Calendar is not connected. "
            "Ask the user to connect Google Calendar in the Calendar Providers settings."
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logger.info("Google token expired, refreshing...")
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
            logger.info("Google token refreshed and saved")
        else:
            raise RuntimeError(
                "Google Calendar token is invalid. "
                "Please reconnect Google Calendar in the Calendar Providers settings."
            )
    return creds


def get_service(api: str, version: str):
    """Return an authenticated Google API service client."""
    logger.debug(f"Building Google service: api={api!r} version={version!r}")
    return build(api, version, credentials=get_google_creds())


def get_user_info() -> dict:
    """Return the authenticated user's profile: name, given_name, email, picture."""
    logger.debug("Fetching Google user info")
    service = build('oauth2', 'v2', credentials=get_google_creds())
    info = service.userinfo().get().execute()
    logger.debug(f"Google user info fetched: email={info.get('email', '?')}")
    return info
