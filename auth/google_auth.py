import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://mail.google.com/'
]


def get_google_creds():
    """Handles OAuth2 authentication with Google Calendar and returns a service client."""
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def get_service(api: str, version: str):
    """Returns an authenticated Google API service client.

    Examples:
        get_service('calendar', 'v3')
        get_service('gmail', 'v1')
    """
    return build(api, version, credentials=get_google_creds())
