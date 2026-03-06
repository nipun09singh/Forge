"""Google Calendar integration — create, list, and manage calendar events.

Configure via environment variables:
    GOOGLE_CALENDAR_API_KEY or GOOGLE_SERVICE_ACCOUNT_JSON
If not set, runs in mock mode.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)

# Mock calendar store
_mock_events: list[dict] = []


async def _calendar_action(action: str, title: str = "", date: str = "",
                           time: str = "", duration_minutes: int = 60,
                           attendees: str = "", event_id: str = "",
                           calendar_id: str = "primary") -> str:
    """Execute a calendar action (create_event, list_events, delete_event, check_availability)."""
    api_key = os.environ.get("GOOGLE_CALENDAR_API_KEY", "")

    if not api_key:
        # Mock mode
        if action == "create_event":
            event = {
                "id": f"evt_{uuid.uuid4().hex[:8]}",
                "title": title,
                "date": date or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "time": time or "10:00",
                "duration_minutes": duration_minutes,
                "attendees": [a.strip() for a in attendees.split(",") if a.strip()],
                "status": "confirmed",
                "created_at": datetime.now().isoformat(),
            }
            _mock_events.append(event)
            return json.dumps({
                "success": True, "mock": True, "event": event,
                "message": "Event created (mock — set GOOGLE_CALENDAR_API_KEY for real calendar)",
            })

        elif action == "list_events":
            target_date = date or datetime.now().strftime("%Y-%m-%d")
            events = [e for e in _mock_events if e.get("date", "") >= target_date]
            if not events:
                events = [
                    {"id": f"evt_mock_{i}", "title": t, "date": (datetime.now() + timedelta(days=i+1)).strftime("%Y-%m-%d"),
                     "time": f"{9+i}:00", "duration_minutes": 60, "status": "confirmed"}
                    for i, t in enumerate(["Team standup", "Client call", "Sprint review"])
                ]
            return json.dumps({"success": True, "mock": True, "events": events[:10]})

        elif action == "delete_event":
            for i, e in enumerate(_mock_events):
                if e.get("id") == event_id:
                    _mock_events.pop(i)
                    return json.dumps({"success": True, "mock": True, "deleted": event_id})
            return json.dumps({"success": False, "error": f"Event {event_id} not found"})

        elif action == "check_availability":
            return json.dumps({
                "success": True, "mock": True,
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "available_slots": [
                    {"time": f"{h:02d}:00", "duration_minutes": 60}
                    for h in [9, 11, 14, 16] if f"{h:02d}:00" != time
                ],
            })

        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    # Real Google Calendar API would go here
    return json.dumps({"success": False, "error": "Real Google Calendar API not yet implemented. Set up mock mode."})


def create_calendar_tool() -> Tool:
    """Create the Google Calendar tool."""
    return Tool(
        name="calendar",
        description="Manage calendar events. Supports: create_event, list_events, delete_event, check_availability. Uses mock mode if GOOGLE_CALENDAR_API_KEY is not set.",
        parameters=[
            ToolParameter(name="action", type="string", description="Action: create_event, list_events, delete_event, check_availability", required=True),
            ToolParameter(name="title", type="string", description="Event title (for create_event)", required=False),
            ToolParameter(name="date", type="string", description="Date in YYYY-MM-DD format", required=False),
            ToolParameter(name="time", type="string", description="Time in HH:MM format", required=False),
            ToolParameter(name="duration_minutes", type="integer", description="Duration in minutes (default: 60)", required=False),
            ToolParameter(name="attendees", type="string", description="Comma-separated attendee emails", required=False),
            ToolParameter(name="event_id", type="string", description="Event ID (for delete_event)", required=False),
        ],
        _fn=_calendar_action,
    )
