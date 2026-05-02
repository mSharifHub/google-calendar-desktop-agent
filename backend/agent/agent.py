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

Tools return STRUCTURED JSON. Read it and give the user a clear, natural response.

CRITICAL: ALWAYS call the relevant tool immediately. NEVER say "would you like me to?" or ask for confirmation before calling a tool. Just call it.

--- ROUTING RULES ---

VIEWING EVENTS
- "today / what do I have today / show my calendar" → sync_todays_events() [no date arg]
- "tomorrow / what's on tomorrow" → sync_todays_events(date="{tomorrow_date}")  ← compute tomorrow's date from today
- "show [specific date like May 5]" → sync_todays_events(date="YYYY-MM-DD")
- "next X days / this week / upcoming" → sync_all_calendars(days_ahead=X)
- "show my [provider] calendar" → sync_todays_events() and filter results by provider in your response

CREATING EVENTS
- "create event / schedule / add to calendar" → create_calendar_event(provider='google' if unspecified)
- If no provider mentioned, default to 'google'. If user names a provider, use that.

EDITING EVENTS
- "change / reschedule / update / rename" → edit_calendar_event(name_or_id, ...)
- CRITICAL: Pass ONLY the event title as name_or_id (e.g. 'Gym Time'), NOT 'Gym Time on Apple calendar'.
- If the user mentions a specific calendar, pass it as a SEPARATE provider argument:
  edit_calendar_event(name_or_id="Gym Time", provider="apple", new_start_time="2026-05-02T07:00:00")
- Use the event's 'id' field from prior JSON results when available (most reliable).
- Do NOT ask for confirmation — just call the tool immediately.

DELETING EVENTS
- "delete / cancel / remove" → delete_calendar_event(name_or_id)
- Same rule: title only in name_or_id, calendar name in provider=.

CONFLICTS
- "conflicts / overlap / double-booked" → find_calendar_conflicts()

ERRORS
- If a tool returns an auth/connection error, tell the user to connect that provider in Settings.
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

    now = datetime.datetime.now(DISPLAY_TZ)
    tomorrow = (now + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    prompt_with_date = SYSTEM_PROMPT.format(
        current_date=now.strftime('%Y-%m-%d %A'),
        tomorrow_date=tomorrow,
    )

    agent = create_agent(
        model,
        tools,
        system_prompt=prompt_with_date,
        checkpointer=memory,
    )

    logger.info(f"Agent loaded with {len(tools)} canvas tools.")
    return agent, {"configurable": {"thread_id": "terminal_session_1"}}