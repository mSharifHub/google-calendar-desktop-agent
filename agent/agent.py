import datetime

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent
from tools.calendar_tools import create_event,edit_event, get_upcoming_events
from tools.jobs_tools import view_job_tracker, scan_job_emails


tools = [
    create_event,
    edit_event,
    get_upcoming_events,
    view_job_tracker,
    scan_job_emails,
]


current_date = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


system_prompt = (
        f"You are an agent whose job is to check users gmail for job applications and help user schedule, check, and update job application statuses and events."
        f" Today's date/time is {current_date}. "
        "You have full access to the user's Google Calendar and an internal Job Application Tracker. "
        "Use the provided tools to check schedules, create meetings, and check or update job application statuses. "
        "Always use get_upcoming_events to find an Event ID before attempting to use edit_event."
    )


memory = MemorySaver()

model = ChatOllama(model="llama3.1", temperature=0)


agent = create_agent(
        model,
        tools,
        system_prompt = system_prompt,
        checkpointer=memory
    )

config = {"configurable": {"thread_id": "terminal_session_1"}}