import re
import datetime
from langchain_core.tools import tool
from auth.google_auth import get_service
from utils.file_store import load_job_tracker, save_job_tracker

# Enhanced keyword sets
INTERVIEW_KEYWORDS = ["interview", "phone screen", "technical screen", "schedule", "availability", "coderpad",
                      "hackerrank", "take-home", "onsite", "invite", "zoom meeting schedule", "coding assessment"]
REJECTION_KEYWORDS = ["unfortunately", "not moving forward", "other candidates", "we regret", "not selected",
                      "decided not", "position has been filled", "pursue other", "chose other candidates"]
OFFER_KEYWORDS = ["offer letter", "job offer", "pleased to offer", "start date",
                  "compensation package"]

STATUS_RANK = {"Applied": 1, "Interview": 2, "Rejected": 3, "Offer": 4}


def _extract_company(sender: str, subject: str) -> str | None:
    """Extract company name from sender domain or subject line."""
    # Try domain extraction first
    domain_match = re.search(r'@([\w.-]+)\.', sender)
    if domain_match:
        domain = domain_match.group(1).lower()
        # Filter out common ATS providers to get the actual company
        ats_providers = ['greenhouse', 'lever', 'workday', 'myworkday', 'ashbyhq', 'smartrecruiters']
        parts = domain.split('.')
        for part in parts:
            if part not in ats_providers:
                return part.capitalize()
    return None


def _determine_status(text: str) -> str:
    text = text.lower()
    if any(kw in text for kw in OFFER_KEYWORDS): return "Offer"
    if any(kw in text for kw in REJECTION_KEYWORDS): return "Rejected"
    if any(kw in text for kw in INTERVIEW_KEYWORDS): return "Interview"
    return "Applied"


@tool
def scan_job_emails(max_results: int = 50) -> str:
    """
    Scans Gmail for job updates, parses the full body for status, and records the application date.
    """
    service = get_service('gmail', 'v1')

    # Broad query to ensure we catch all relevant threads
    query = '("application" OR "interview" OR "opportunity") newer_than:90d'

    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No recent job-related emails found."

        tracker = load_job_tracker()
        updates_made = 0

        for msg in messages:
            # We fetch 'full' format here to get the full body if snippet isn't enough
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()

            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '').lower()
            date_raw = next((h['value'] for h in headers if h['name'] == 'Date'), '')

            # Simple date parsing
            try:
                date_obj = datetime.datetime.strptime(date_raw.split(', ')[-1][:11], '%d %b %Y')
                date_str = date_obj.strftime('%Y-%m-%d')
            except:
                date_str = "Unknown"

            snippet = msg_data.get('snippet', '')
            # Get full text body if available
            body = ""
            payload = msg_data.get('payload', {})
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        import base64
                        body = base64.urlsafe_b64decode(part['body'].get('data', '')).decode('utf-8', 'ignore')

            company = _extract_company(sender, subject)
            if not company: continue

            # Analyze status using snippet + full body
            status = _determine_status(subject + " " + snippet + " " + body)

            # Logic: Only update if the new status is a higher "rank" or if it's a new company
            current = tracker["applications"].get(company, {})
            current_status = current.get("status", "Applied")

            if company not in tracker["applications"] or STATUS_RANK.get(status, 0) >= STATUS_RANK.get(current_status,
                                                                                                       0):
                tracker["applications"][company] = {
                    "status": status,
                    "date_updated": date_str
                }
                updates_made += 1

        save_job_tracker(tracker)
        return f"Job tracker synced! {updates_made} updates made. Database now has {len(tracker['applications'])} companies."

    except Exception as e:
        return f"Error scanning job emails: {str(e)}"


@tool
def get_job_applications(company: str = "") -> str:
    """
    Returns job application statuses from the local tracker.
    Optionally filter by company name. Leave company empty to get all applications.
    """
    tracker = load_job_tracker()
    applications = tracker.get("applications", {})

    if not applications:
        return "No job applications found in tracker. Try running scan_job_emails first to sync from Gmail."

    if company:
        key = next((k for k in applications if company.lower() in k.lower()), None)
        if not key:
            return f"No application found for '{company}' in the tracker."
        data = applications[key]
        return f"{key}: Status={data.get('status', 'Unknown')}, Last Updated={data.get('date_updated', 'Unknown')}"

    lines = [f"- {name}: Status={info.get('status', 'Unknown')}, Last Updated={info.get('date_updated', 'Unknown')}"
             for name, info in applications.items()]
    return "Job Applications:\n" + "\n".join(lines)