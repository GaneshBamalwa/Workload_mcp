"""Google Calendar connector for event ingestion.

NOTE: google-api-python-client is synchronous. All API calls are wrapped
in asyncio.to_thread() so they don't block the MCP event loop.

Authentication: same GOOGLE_ACCESS_TOKEN + GOOGLE_REFRESH_TOKEN as Gmail.
Run `python scripts/get_google_token.py` once to set them up.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

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

    def _get_creds(self) -> Credentials:
        """Build and (if needed) refresh Google credentials."""
        from app.core.config import settings

        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=CALENDAR_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.access_token = creds.token
        return creds

    def _build_service(self):
        creds = self._get_creds()
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    async def test_connection(self) -> bool:
        """Test Calendar connection."""
        try:
            svc = await asyncio.to_thread(self._build_service)
            await asyncio.to_thread(
                lambda: svc.calendarList().list(maxResults=1).execute()
            )
            logger.info("Calendar connection test successful")
            return True
        except Exception as e:
            logger.error("Calendar connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get upcoming events from Google Calendar (next 7 days)."""
        try:
            svc = await asyncio.to_thread(self._build_service)

            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()

            kwargs: dict[str, Any] = {
                "calendarId": "primary",
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": min(limit, 250),
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if sync_cursor:
                kwargs["updatedMin"] = sync_cursor

            result = await asyncio.to_thread(
                lambda: svc.events().list(**kwargs).execute()
            )
            events: list[dict] = result.get("items", [])
            next_cursor = result.get("nextSyncToken")

            # Filter out cancelled events
            events = [e for e in events if e.get("status") != "cancelled"]

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

            # Parse start/end
            start_info = item.get("start", {})
            end_info = item.get("end", {})

            start_time = None
            end_time = None
            if "dateTime" in start_info:
                start_time = datetime.fromisoformat(start_info["dateTime"].replace("Z", "+00:00"))
            elif "date" in start_info:
                start_time = datetime.fromisoformat(start_info["date"])

            if "dateTime" in end_info:
                end_time = datetime.fromisoformat(end_info["dateTime"].replace("Z", "+00:00"))

            effort_minutes = None
            if start_time and end_time:
                effort_minutes = int((end_time - start_time).total_seconds() / 60)

            attendees = item.get("attendees", [])
            is_meeting = len(attendees) > 1
            organizer = item.get("organizer", {})
            created_by = organizer.get("email")

            category = "meeting" if is_meeting else "calendar_event"

            work_item = UnifiedWorkItem(
                source="calendar",
                source_id=event_id,
                title=f"[Meeting] {summary}" if is_meeting else f"[Event] {summary}",
                description=description or None,
                due_date=start_time,
                estimated_effort_minutes=effort_minutes,
                created_by=created_by,
                urgency=0.8 if is_meeting else 0.5,
                importance=0.85 if is_meeting else 0.6,
                requires_deep_work=False,
                confidence_score=0.95,
                category=category,
                stakeholders=[a.get("email") for a in attendees if a.get("email")],
                metadata={
                    "event_id": event_id,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "is_meeting": is_meeting,
                    "attendee_count": len(attendees),
                    "organizer": created_by,
                    "location": item.get("location"),
                    "meet_link": item.get("hangoutLink"),
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
        access_token: str, user_id: str, refresh_token: Optional[str] = None
    ) -> CalendarConnector:
        return CalendarConnector(access_token, user_id, refresh_token)
