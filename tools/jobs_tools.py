import re
from langchain_core.tools import tool
from auth.google_auth import get_service
from utils.file_store import load_job_tracker, save_job_tracker


INTERVIEW_KEYWORDS  = ["interview", "phone screen", "technical screen", "schedule", "availability", "coderpad", "hackerrank", "take-home", "onsite"]
REJECTION_KEYWORDS  = ["unfortunately", "not moving forward", "other candidates", "we regret", "not selected", "decided not", "position has been filled"]
OFFER_KEYWORDS      = ["offer letter", "job offer", "pleased to offer", "background check", "start date", "compensation package"]


def _extract_company(sender: str, subject: str) -> str | None:
    """Extract company name from sender domain or subject line."""
    domain_match = re.search(r'@([\w.-]+)\.', sender)
    if not domain_match:
        return None
    domain_parts = domain_match.group(1).lower().split('.')
    company = domain_parts[-1] if len(domain_parts) > 1 else domain_parts[0]
    return company.capitalize()


def _determine_status(subject: str, snippet: str) -> str:
    combined = subject + " " + snippet
    if any(kw in combined for kw in OFFER_KEYWORDS):
        return "Offer"
    if any(kw in combined for kw in REJECTION_KEYWORDS):
        return "Rejected"
    if any(kw in combined for kw in INTERVIEW_KEYWORDS):
        return "Interview"
    return "Applied"


@tool
def scan_job_emails(max_results: int = 50) -> str:
    """
    Scans the user's Gmail for job application updates, interviews, and rejections,
    and updates the local job tracker database automatically.
    """
    service = get_service('gmail', 'v1')

    query = (
        'subject:("application received" OR "thank you for applying" OR "your application" OR '
        '"we received your application" OR "interview" OR "phone screen" OR "technical screen" OR '
        '"we regret" OR "not moving forward" OR "unfortunately" OR "offer letter" OR "job offer") '
        'newer_than:90d'
    )

    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No recent job-related emails found."

        tracker = load_job_tracker()
        updates_made = 0

        for msg in messages:
            msg_data = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['Subject', 'From']
            ).execute()

            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender  = next((h['value'] for h in headers if h['name'] == 'From'), '').lower()
            snippet = msg_data.get('snippet', '')

            company = _extract_company(sender, subject)
            if not company:
                continue

            status = _determine_status(subject.lower(), snippet.lower())

            tracker["applications"][company] = {"status": status}
            updates_made += 1

        save_job_tracker(tracker)
        return f"Job tracker synced! {updates_made} updates across {len(tracker['applications'])} companies."

    except Exception as e:
        return f"Error scanning job emails: {str(e)}"


@tool
def view_job_tracker(status_filter: str = "all") -> str:
    """
    Retrieves the user's job application tracker.
    Pass a status_filter (e.g., 'Rejected', 'Interview', 'Applied', 'all') to see specific jobs.
    """
    tracker = load_job_tracker()
    apps = tracker.get("applications", {})

    if not apps:
        return "Your job tracker is currently empty. Run scan_job_emails first."

    filtered_apps = []
    for company, data in apps.items():
        status = data.get("status", "Unknown")
        if status_filter.lower() == "all" or status.lower() == status_filter.lower():
            filtered_apps.append(f"- {company}: {status}")

    if not filtered_apps:
        return f"No applications found with status: {status_filter}."

    header = f"Job Applications ({status_filter}) — {len(filtered_apps)} total:\n"
    return header + "\n".join(filtered_apps)