import datetime

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent
from tools.calendar_tools import create_event, edit_event, get_upcoming_events, get_todays_events
from tools.jobs_tools import scan_job_emails, get_job_applications


tools = [
    create_event,
    edit_event,
    get_upcoming_events,
    get_todays_events,
    scan_job_emails,
    get_job_applications,
]


current_date = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


system_prompt = (
        f"You are an agent whose job is to check users gmail for job applications and help user schedule, check, and update job application statuses and events."
        f" Today's date/time is {current_date}. "
        "You have full access to the user's Google Calendar and an internal Job Application Tracker. "
        "Use the provided tools to check schedules, create meetings, and check or update job application statuses. "
        "When the user asks about today's events or what is on their calendar today, always call get_todays_events. "
        "Only use get_upcoming_events when the user explicitly asks for upcoming or future events. "
        "Always use get_upcoming_events to find an Event ID before attempting to use edit_event. "
        "To show job applications, always call get_job_applications — never guess or fabricate application data. "
        "If get_job_applications returns no results, call scan_job_emails first to sync from Gmail, then call get_job_applications again."
    )


memory = MemorySaver()

model = ChatOllama(model="llama3.1:latest", temperature=0)


agent = create_agent(
        model,
        tools,
        system_prompt = system_prompt,
        checkpointer=memory
    )

config = {"configurable": {"thread_id": "terminal_session_1"}}