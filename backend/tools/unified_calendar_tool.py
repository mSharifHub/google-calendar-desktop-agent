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


def _find_event(name_or_id: str, events: List[UnifiedEvent],
                provider: str = None) -> UnifiedEvent:
    """
    Find a single event by exact ID or case-insensitive title substring.
    Pass provider ('google', 'apple', 'outlook', 'calendly') to disambiguate
    when the same event title exists in multiple calendars.
    """
    # Optionally narrow to one provider first
    pool = [e for e in events if e.provider == provider.lower()] if provider else events

    matches = [e for e in pool if e.id == name_or_id or name_or_id.lower() in e.title.lower()]
    if not matches and provider:
        # Broaden to all providers if the provider filter produced nothing
        logger.warning(f"No match for '{name_or_id}' in provider '{provider}', searching all providers.")
        matches = [e for e in events if e.id == name_or_id or name_or_id.lower() in e.title.lower()]
    if not matches:
        raise ValueError(f"No event found matching '{name_or_id}'.")
    if len(matches) > 1:
        details = ", ".join(f"[{e.provider}] {e.title} ({e.start.date()})" for e in matches)
        raise ValueError(f"Multiple events match '{name_or_id}': {details}. Provide the exact ID.")
    return matches[0]


@tool
def sync_todays_events(date: str = None) -> str:
    """
    Fetch events for a specific date from all connected calendars. Returns JSON.
    - Omit 'date' (or pass None) for TODAY's events.
    - Pass 'date' as 'YYYY-MM-DD' for any other day, including tomorrow.
    Call this immediately whenever the user asks about any specific day — never ask first.
    """
    if date:
        try:
            target = datetime.date.fromisoformat(date)
        except ValueError:
            target = datetime.datetime.now(DISPLAY_TZ).date()
    else:
        target = datetime.datetime.now(DISPLAY_TZ).date()

    day_start = datetime.datetime(target.year, target.month, target.day,
                                  0, 0, 0, tzinfo=DISPLAY_TZ).astimezone(datetime.timezone.utc)
    day_end   = datetime.datetime(target.year, target.month, target.day,
                                  23, 59, 59, tzinfo=DISPLAY_TZ).astimezone(datetime.timezone.utc)

    today = datetime.datetime.now(DISPLAY_TZ).date()
    days_needed = max((target - today).days + 2, 2)

    all_events = get_all_events(days_ahead=days_needed)
    day_events = [e for e in all_events if day_start <= e.start <= day_end]
    return json.dumps([e.to_dict() for e in day_events], indent=2)


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
    events = get_all_events(days_ahead)
    conflicts = find_conflicts(events)
    out = [{"conflict_1": a.to_dict(), "conflict_2": b.to_dict()} for a, b in conflicts]
    return json.dumps(out, indent=2)


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
def edit_calendar_event(name_or_id: str, provider: str = None,
                        new_summary: str = None, new_start_time: str = None,
                        new_end_time: str = None, new_description: str = None,
                        new_location: str = None) -> str:
    """
    Find and edit an event across all connected calendars.
    - name_or_id: the event title (e.g. 'Gym Time') or its exact ID. Do NOT include
                  calendar name here — use the 'provider' argument for that.
    - provider:   optional — 'google', 'apple', 'outlook', or 'calendly'.
                  Use this when the user specifies which calendar (e.g. 'on Apple calendar').
    - Times must be ISO 8601 format: '2026-05-02T09:00:00'
    """
    events = get_all_events(days_ahead=60)
    logger.info(f"edit_calendar_event: searching for '{name_or_id}' provider={provider!r}")
    try:
        event = _find_event(name_or_id, events, provider=provider)
    except ValueError as e:
        logger.warning(f"edit_calendar_event: {e}")
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
def delete_calendar_event(name_or_id: str, provider: str = None) -> str:
    """
    Find and delete an event across all connected calendars.
    - name_or_id: event title or exact ID. Do NOT include calendar name here.
    - provider:   optional — 'google', 'apple', 'outlook', or 'calendly'.
    """
    events = get_all_events(days_ahead=60)
    logger.info(f"delete_calendar_event: searching for '{name_or_id}' provider={provider!r}")
    try:
        event = _find_event(name_or_id, events, provider=provider)
    except ValueError as e:
        logger.warning(f"delete_calendar_event: {e}")
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