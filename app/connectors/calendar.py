"""Google Calendar connector for calendar event ingestion."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Calendar scopes
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]


class CalendarConnector(BaseConnector):
    """Google Calendar connector for event ingestion."""

    connector_type = "calendar"
    scope_required = CALENDAR_SCOPES

    def __init__(self, access_token: str, user_id: str, refresh_token: Optional[str] = None):
        """Initialize Calendar connector."""
        super().__init__(access_token, user_id)
        self.refresh_token = refresh_token
        self._service = None

    @property
    def service(self):
        """Get Calendar service."""
        if not self._service:
            creds = Credentials(self.access_token, refresh_token=self.refresh_token)
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    async def test_connection(self) -> bool:
        """Test Calendar connection."""
        try:
            calendars = self.service.calendarList().list(maxResults=1).execute()
            logger.info("Calendar connection test successful")
            return True
        except Exception as e:
            logger.error("Calendar connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get events from Google Calendar."""
        try:
            # Get primary calendar ID
            calendars = self.service.calendarList().list().execute()
            calendar_id = calendars["items"][0]["id"]

            # Get events for next 7 days (excluding past events)
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()

            kwargs = {
                "calendarId": calendar_id,
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": min(limit, 250),
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if sync_cursor:
                kwargs["updatedMin"] = sync_cursor

            results = self.service.events().list(**kwargs).execute()
            events = results.get("items", [])
            next_cursor = results.get("nextSyncToken")

            logger.info("Fetched events from Calendar", count=len(events))
            return events, next_cursor

        except Exception as e:
            logger.error("Calendar fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Calendar event to unified work item."""
        try:
            summary = item.get("summary", "(No Title)")
            description = item.get("description", "")
            event_id = item.get("id", "")

            # Parse start/end times
            start_info = item.get("start", {})
            end_info = item.get("end", {})

            start_time = None
            end_time = None
            if "dateTime" in start_info:
                start_time = datetime.fromisoformat(start_info["dateTime"].replace("Z", "+00:00"))
            if "dateTime" in end_info:
                end_time = datetime.fromisoformat(end_info["dateTime"].replace("Z", "+00:00"))

            # Calculate duration
            estimated_effort_minutes = None
            if start_time and end_time:
                estimated_effort_minutes = int((end_time - start_time).total_seconds() / 60)

            # Determine meeting status
            attendees = item.get("attendees", [])
            is_meeting = len(attendees) > 1

            # Extract organizer
            organizer = item.get("organizer", {})
            created_by = organizer.get("email")

            # Determine category
            event_type = item.get("eventType", "default")
            if is_meeting:
                category = "meeting"
            elif event_type == "workingLocation":
                category = "focus_block"
            else:
                category = "calendar_event"

            # Create unified work item
            work_item = UnifiedWorkItem(
                source="calendar",
                source_id=event_id,
                title=summary,
                description=description if description else None,
                due_date=start_time,
                estimated_effort_minutes=estimated_effort_minutes,
                created_by=created_by,
                requires_deep_work=category == "focus_block",
                confidence_score=0.95,
                category=category,
                stakeholders=[a.get("email") for a in attendees],
                metadata={
                    "event_id": event_id,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "is_meeting": is_meeting,
                    "attendees": len(attendees),
                    "organizer": created_by,
                    "location": item.get("location"),
                },
            )

            return work_item.to_dict()

        except Exception as e:
            logger.error("Calendar event normalization failed", error=str(e))
            raise


class CalendarConnectorFactory:
    """Factory for creating Calendar connectors."""

    @staticmethod
    def create_from_oauth(
        access_token: str,
        user_id: str,
        refresh_token: Optional[str] = None,
    ) -> CalendarConnector:
        """Create connector from OAuth tokens."""
        return CalendarConnector(access_token, user_id, refresh_token)
