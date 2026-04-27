import base64
from email.message import EmailMessage
from googleapiclient.discovery import build

from langchain_core.tools import tool
from auth.google_auth import get_google_creds

@tool
def send_email(to_address: str, subject: str, body: str) -> str:
    """
    Composes and sends an email to the specified address.
    message['From'] = 'me' # 'me' tells the API to use the authenticated user's address
    """
    creds = get_google_creds()
    service = build('gmail', 'v1', credentials=creds)

    try:
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to_address
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        send_message = service.users().messages().send(userId='me', body=create_message).execute()
        return f"Email successfully sent to {to_address}. Message ID: {send_message.get('id')}"
    except Exception as e:
        return f"Error sending email: {str(e)}"


@tool
def search_emails(query:str = "is:unread", max_results: int = 10) -> str:
    """
        Searches the user's Gmail inbox.
        You can use standard Gmail search queries in the 'query' parameter (e.g., 'is:unread', 'from:person@example.com', 'subject:meeting').
    """
    creds = get_google_creds()
    service = build('gmail', 'v1', credentials=creds)

    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No emails found matching the query."

        emails_lists = []

        for msg in messages:

            msg_data = (service.users().messages()
                        .get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From'])
                        .execute())
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'No Subject')
            sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
            snippet = msg_data.get('snippet', '')

            emails_lists.append(f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}")

        return "\n---\n".join(emails_lists)

    except Exception as e:
        return f"Error searching emails: {str(e)}"




