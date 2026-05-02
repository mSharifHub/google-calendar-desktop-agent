from __future__ import annotations
import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("America/Los_Angeles")

@dataclass
class UnifiedEvent:
    id: str
    title: str
    start: datetime.datetime
    end: datetime.datetime
    provider: str
    location: str = ""
    description: str = ""
    is_all_day: bool = False

    def to_dict(self) -> dict:
        """Serializes the event for JSON consumption by the LLM."""
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.astimezone(DISPLAY_TZ).strftime('%Y-%m-%d %I:%M %p %Z'),
            "end": self.end.astimezone(DISPLAY_TZ).strftime('%Y-%m-%d %I:%M %p %Z'),
            "provider": self.provider,
            "location": self.location,
            "description": self.description,
            "is_all_day": self.is_all_day
        }

def _to_utc(dt: datetime.datetime) -> datetime.datetime:
    """Converts a datetime object to UTC, assuming naive datetimes are already in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)

def _parse_dt(raw: str) -> datetime.datetime:
    """Parses a string into a datetime object, handling different ISO 8601 formats."""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")