from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from tools.calendar_tools import create_event,edit_event, get_upcoming_events
from tools.jobs_tools import view_job_tracker, scan_job_emails


tools = [
    create_event,
    edit_event,
    get_upcoming_events,
    view_job_tracker,
    scan_job_emails,
]



