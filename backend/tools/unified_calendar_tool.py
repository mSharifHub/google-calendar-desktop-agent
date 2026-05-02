from __future__ import annotations

import datetime
import logging
import json
from typing import List, Tuple

from langchain_core.tools import tool

from tools.unified_event import UnifiedEvent, DISPLAY_TZ
from tools.google_calendar_tools import    fetch_google_events, edit_google_event, delete_google_event, create_google_event
from tools.outlook_tools import fetch_outlook_events, edit_outlook_event, delete_outlook_event, create_outlook_event
from tools.apple_calendar_tools import fetch_apple_events, edit_apple_event, delete_apple_event, create_apple_event
from tools.calendly_tools import fetch_calendly_events

logger = logging.getLogger(__name__)


def get_all_events(days_ahead: int = 7) -> List[UnifiedEvent]:
    """Fetch and merge events from all connected providers."""
    logger.info(f"Fetching all events for the next {days_ahead} days.")
    events = (
            fetch_google_events(days_ahead) +
            fetch_outlook_events(days_ahead) +
            fetch_apple_events(days_ahead) +
            fetch_calendly_events(days_ahead)
    )
    return sorted(events, key=lambda e: e.start)


def find_conflicts(events: List[UnifiedEvent]) -> List[Tuple[UnifiedEvent, UnifiedEvent]]:
    """Return pairs of events that overlap."""
    return [(events[i], events[j]) for i in range(len(events)) for j in range(i + 1, len(events)) if
            events[i].start < events[j].end and events[j].start < events[i].end]


def _find_event(name_or_id: str, events: List[UnifiedEvent]) -> UnifiedEvent:
    """Find a single event by ID or name."""
    matches = [e for e in events if e.id == name_or_id or name_or_id.lower() in e.title.lower()]
    if not matches:
        raise ValueError(f"No event found matching '{name_or_id}'.")
    if len(matches) > 1:
        raise ValueError(f"Multiple events match '{name_or_id}'. Try using the exact ID.")
    return matches[0]


@tool
def sync_todays_events() -> str:
    """Fetches today's events from all connected calendars. Returns structured JSON data."""
    now_local = datetime.datetime.now(DISPLAY_TZ)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc)
    today_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(datetime.timezone.utc)

    events = get_all_events(days_ahead=2)
    today_events = [e for e in events if today_start <= e.start <= today_end]

    return json.dumps([e.to_dict() for e in today_events], indent=2)


@tool
def sync_all_calendars(days_ahead: int = 7) -> str:
    """Fetches all events from all connected calendars for the specified days ahead. Returns JSON data."""
    events = get_all_events(days_ahead)
    return json.dumps([e.to_dict() for e in events], indent=2)


@tool
def find_calendar_conflicts(days_ahead: int = 7) -> str:
    """Finds scheduling conflicts across all connected calendars. Returns JSON data."""
    events = get_all_events(days_ahead)
    conflicts = find_conflicts(events)
    out = [{"conflict_1": a.to_dict(), "conflict_2": b.to_dict()} for a, b in conflicts]
    return json.dumps(out, indent=2)


@tool
def resolve_calendar_conflicts(days_ahead: int = 7, strategy: str = "priority") -> str:
    """Analyzes and suggests resolutions for calendar conflicts."""
    # Simplified to return the JSON of conflicts; LLM Orchestrator will figure out the resolution
    return find_calendar_conflicts(days_ahead)


@tool
def create_calendar_event(summary: str, start_time: str, end_time: str, provider: str = "google",
                          description: str = None, location: str = None) -> str:
    """
    Create a new event in the specified calendar provider.
    Valid providers are 'google', 'outlook', or 'apple'. Defaults to 'google'.
    """
    p = provider.lower()
    logger.info(f"Routing create event '{summary}' to provider {p}")

    if p == "google": return json.dumps(
        {"status": create_google_event(summary, start_time, end_time, description, location)})
    if p == "outlook": return json.dumps(
        {"status": create_outlook_event(summary, start_time, end_time, description, location)})
    if p == "apple": return json.dumps(
        {"status": create_apple_event(summary, start_time, end_time, description, location)})

    return json.dumps({"error": f"Unsupported provider '{provider}'."})


@tool
def edit_calendar_event(name_or_id: str, new_summary: str = None, new_start_time: str = None, new_end_time: str = None,
                        new_description: str = None, new_location: str = None) -> str:
    """Find and edit an event across all connected calendars. Provide the event ID."""
    events = get_all_events(days_ahead=60)
    try:
        event = _find_event(name_or_id, events)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if event.provider == "google":
        res = edit_google_event(event.id, new_summary, new_start_time, new_end_time, new_description, new_location)
    elif event.provider == "outlook":
        res = edit_outlook_event(event.id, new_summary, new_start_time, new_end_time, new_description, new_location)
    elif event.provider == "apple":
        res = edit_apple_event(event.id, new_summary, new_start_time, new_end_time, new_description, new_location)
    else:
        res = f"Editing not supported for {event.provider}"

    return json.dumps({"status": res})


@tool
def delete_calendar_event(name_or_id: str) -> str:
    """Find and delete an event across all connected calendars."""
    events = get_all_events(days_ahead=60)
    try:
        event = _find_event(name_or_id, events)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if event.provider == "google":
        res = delete_google_event(event.id)
    elif event.provider == "outlook":
        res = delete_outlook_event(event.id)
    elif event.provider == "apple":
        res = delete_apple_event(event.id)
    else:
        res = f"Deletion not supported for {event.provider}"

    return json.dumps({"status": res})