import datetime
import logging
import json
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from tools.unified_calendar_tool import (
    sync_all_calendars,
    sync_todays_events,
    find_calendar_conflicts,
    resolve_calendar_conflicts,
    delete_calendar_event,
    edit_calendar_event,
    create_calendar_event
)

logger = logging.getLogger(__name__)
DISPLAY_TZ = ZoneInfo("America/Los_Angeles")

SYSTEM_PROMPT = """You are a highly capable AI Calendar Orchestrator.
Today's date is {current_date}.

You are connected to a unified calendar tool that abstracts Google, Outlook, Apple, and Calendly.
The tools will return STRUCTURED JSON DATA. You must read this data and formulate a natural, helpful response for the user.

--- ROUTING RULES ---
- "show my calendar / what do I have today" → Call `sync_todays_events`.
- "show my schedule for the next X days" → Call `sync_all_calendars`.
- "schedule a meeting" → Call `Calendar`. If the user doesn't specify a provider, default to 'google'.
- "delete/cancel" → Call `delete_calendar_event`. Use the exact 'id' field returned from previous queries.
- "reschedule/edit" → Call `edit_calendar_event`.
- "check for conflicts" → Call `find_calendar_conflicts`.

If a tool returns an error regarding Authentication or Connection, politely inform the user they need to connect that provider in their settings.
"""


def build_agent(model):
    """Builds and configures the calendar agent with appropriate tools."""
    logger.info("Initializing Agentic Canvas...")
    memory = MemorySaver()

    # The Agent ONLY sees the Unified Interface nodes
    tools = [
        sync_todays_events,
        sync_all_calendars,
        find_calendar_conflicts,
        resolve_calendar_conflicts,
        delete_calendar_event,
        edit_calendar_event,
        create_calendar_event
    ]

    prompt_with_date = SYSTEM_PROMPT.format(
        current_date=datetime.datetime.now(DISPLAY_TZ).strftime('%Y-%m-%d %A')
    )

    agent = create_agent(
        model,
        tools,
        system_prompt=prompt_with_date,
        checkpointer=memory,
    )

    logger.info(f"Agent loaded with {len(tools)} canvas tools.")
    return agent, {"configurable": {"thread_id": "terminal_session_1"}}