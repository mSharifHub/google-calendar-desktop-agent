import datetime

from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent
from tools.calendar_tools import create_event, edit_event, get_upcoming_events, get_todays_events

tools = [
    create_event,
    edit_event,
    get_upcoming_events,
    get_todays_events,
]

current_date = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

system_prompt = (
    f"You are a calendar assistant that helps users schedule, check, and manage their events."
    f" Today's date/time is {current_date}. "
    "You have full access to the user's Google Calendar. "
    "Use the provided tools to check schedules and create or update events. "
    "When the user asks about today's events or what is on their calendar today, always call get_todays_events. "
    "Only use get_upcoming_events when the user explicitly asks for upcoming or future events. "
    "Always use get_upcoming_events to find an Event ID before attempting to use edit_event."
)


def build_agent(model):
    memory = MemorySaver()
    agent = create_agent(
        model,
        tools,
        system_prompt=system_prompt,
        checkpointer=memory,
    )
    config = {"configurable": {"thread_id": "terminal_session_1"}}
    return agent, config
