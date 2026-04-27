from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from tools.calendar_tools import create_event,edit_event, get_upcoming_events
from tools.email_tools import send_email, search_emails

tools = [
    create_event,
    edit_event,
    get_upcoming_events,
    search_emails,
    send_email
]



