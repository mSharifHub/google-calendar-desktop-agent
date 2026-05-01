import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


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
    print("[AUTH:google] is_connected() called")
    if not os.path.exists(TOKEN_FILE):
        print("[AUTH:google] is_connected() → False (token.json not found)")
        return False
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        result = creds.valid or (creds.expired and bool(creds.refresh_token))
        print(f"[AUTH:google] is_connected() → {result} (valid={creds.valid}, expired={creds.expired}, has_refresh={bool(creds.refresh_token)})")
        return result
    except Exception as e:
        print(f"[AUTH:google] is_connected() → False (error: {e})")
        return False


def connect():
    """
    Run the full OAuth2 flow (opens a browser) and save the token.
    Blocking — intended to be called inside run_in_executor.
    """
    print("[AUTH:google] connect() → starting OAuth2 flow")
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())
    print("[AUTH:google] connect() → token saved successfully")
    return creds


def disconnect():
    """Remove the cached token, effectively disconnecting Google Calendar."""
    print("[AUTH:google] disconnect() called")
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("[AUTH:google] disconnect() → token.json removed")
    else:
        print("[AUTH:google] disconnect() → token.json not found, nothing to remove")


def get_google_creds():
    """
    Return valid Google credentials, refreshing automatically if expired.
    Raises RuntimeError if the user has not connected Google Calendar yet.
    """
    print("[AUTH:google] get_google_creds() called")
    if not os.path.exists(TOKEN_FILE):
        print("[AUTH:google] get_google_creds() → RuntimeError: token.json missing")
        raise RuntimeError(
            "Google Calendar is not connected. "
            "Ask the user to connect Google Calendar in the Calendar Providers settings."
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("[AUTH:google] get_google_creds() → token expired, refreshing...")
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
            print("[AUTH:google] get_google_creds() → token refreshed and saved")
        else:
            print("[AUTH:google] get_google_creds() → RuntimeError: token invalid, no refresh_token")
            raise RuntimeError(
                "Google Calendar token is invalid. "
                "Please reconnect Google Calendar in the Calendar Providers settings."
            )
    else:
        print("[AUTH:google] get_google_creds() → token valid")
    return creds


def get_service(api: str, version: str):
    """Return an authenticated Google API service client."""
    print(f"[AUTH:google] get_service(api={api!r}, version={version!r}) called")
    service = build(api, version, credentials=get_google_creds())
    print(f"[AUTH:google] get_service() → service built successfully")
    return service


def get_user_info() -> dict:
    """Return the authenticated user's profile: name, given_name, email, picture."""
    print("[AUTH:google] get_user_info() called")
    service = build('oauth2', 'v2', credentials=get_google_creds())
    info = service.userinfo().get().execute()
    print(f"[AUTH:google] get_user_info() → email={info.get('email', '?')}")
    return info
