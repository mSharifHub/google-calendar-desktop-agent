import datetime

from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from tools.unified_calendar import (
    sync_all_calendars,
    sync_todays_events,
    find_calendar_conflicts,
    resolve_calendar_conflicts,
    delete_calendar_event,
    edit_calendar_event,
)

current_date = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

system_prompt = (
    f"You are a calendar assistant that helps users schedule, check, and manage their events."
    f" Today's date/time is {current_date}. "
    "You have access to whichever calendar providers the user has connected "
    "(Google Calendar, Outlook, Apple Calendar, Calendly). "
    "IMPORTANT RULES:\n"
    "1. When the user asks 'show my calendar', 'what's on my calendar', 'what do I have today', "
    "'what's my schedule', or any similar request — ALWAYS call sync_todays_events (for today) "
    "or sync_all_calendars (for a broader view). Never call provider-specific tools for these requests.\n"
    "2. Only use provider-specific tools (get_upcoming_events, get_todays_events, etc.) when the user "
    "explicitly names a specific calendar (e.g. 'show my Google Calendar events').\n"
    "3. When the user asks to delete, remove, or cancel an event — ALWAYS call delete_calendar_event "
    "with the event name or ID. This tool automatically finds which calendar the event belongs to "
    "and deletes it from the correct provider. Never guess the provider or call a provider-specific "
    "delete tool directly.\n"
    "4. When the user asks to change, update, reschedule, or rename an event — ALWAYS call "
    "edit_calendar_event with the event name or ID. This tool finds the event across all providers "
    "using real IDs and edits it in the correct calendar. Never guess an event ID or call a "
    "provider-specific edit tool directly.\n"
    "5. Use find_calendar_conflicts to detect scheduling conflicts across providers.\n"
    "6. Use resolve_calendar_conflicts to suggest how to resolve those conflicts."
)


def build_agent(model):
    print("[AGENT] build_agent() called → initializing agent")
    memory = MemorySaver()

    # Unified cross-provider tools — always present regardless of which providers are connected
    tools = [
        sync_todays_events,
        sync_all_calendars,
        find_calendar_conflicts,
        resolve_calendar_conflicts,
        delete_calendar_event,
        edit_calendar_event,
    ]
    print(f"[AGENT] build_agent() → loaded {len(tools)} unified tools")

    # Google Calendar tools — added only when connected
    try:
        from auth.google_auth import is_connected as google_connected
        if google_connected():
            from tools.calendar_tools import create_event, edit_event, get_upcoming_events, get_todays_events, delete_google_event
            tools += [create_event, edit_event, get_upcoming_events, get_todays_events, delete_google_event]
            print("[AGENT] build_agent() → Google Calendar tools loaded (5 tools)")
        else:
            print("[AGENT] build_agent() → Google Calendar not connected, skipping tools")
    except Exception as e:
        print(f"[AGENT] build_agent() → Google Calendar tools skipped due to error: {e}")

    # Outlook tools — added only when connected
    try:
        from auth.microsoft_auth import is_connected as outlook_connected
        if outlook_connected():
            from tools.outlook_tools import (
                get_outlook_upcoming_events,
                get_outlook_todays_events,
                create_outlook_event,
                edit_outlook_event,
                delete_outlook_event,
            )
            tools += [
                get_outlook_upcoming_events,
                get_outlook_todays_events,
                create_outlook_event,
                edit_outlook_event,
                delete_outlook_event,
            ]
            print("[AGENT] build_agent() → Outlook tools loaded (5 tools)")
        else:
            print("[AGENT] build_agent() → Outlook not connected, skipping tools")
    except Exception as e:
        print(f"[AGENT] build_agent() → Outlook tools skipped due to error: {e}")

    # Apple Calendar tools — added only when connected
    try:
        from auth.apple_auth import is_connected as apple_connected
        if apple_connected():
            from tools.apple_tools import (
                get_apple_upcoming_events,
                get_apple_todays_events,
                create_apple_event,
                delete_apple_event,
            )
            tools += [
                get_apple_upcoming_events,
                get_apple_todays_events,
                create_apple_event,
                delete_apple_event,
            ]
            print("[AGENT] build_agent() → Apple Calendar tools loaded (4 tools)")
        else:
            print("[AGENT] build_agent() → Apple Calendar not connected, skipping tools")
    except Exception as e:
        print(f"[AGENT] build_agent() → Apple Calendar tools skipped due to error: {e}")

    # Calendly tools — added only when connected
    try:
        from auth.calendly_auth import is_connected as calendly_connected
        if calendly_connected():
            from tools.calendly_tools import (
                get_calendly_scheduled_events,
                get_calendly_event_details,
            )
            tools += [
                get_calendly_scheduled_events,
                get_calendly_event_details,
            ]
            print("[AGENT] build_agent() → Calendly tools loaded (2 tools)")
        else:
            print("[AGENT] build_agent() → Calendly not connected, skipping tools")
    except Exception as e:
        print(f"[AGENT] build_agent() → Calendly tools skipped due to error: {e}")

    tool_names = [t.name for t in tools]
    print(f"[AGENT] build_agent() → total {len(tools)} tools registered: {tool_names}")

    agent = create_agent(
        model,
        tools,
        system_prompt=system_prompt,
        checkpointer=memory,
    )
    config = {"configurable": {"thread_id": "terminal_session_1"}}
    print("[AGENT] build_agent() → agent ready")
    return agent, config
