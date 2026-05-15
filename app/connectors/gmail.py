"""Gmail connector for email ingestion."""
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from google.auth.oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Gmail scopes
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailConnector(BaseConnector):
    """Gmail connector for email ingestion."""

    connector_type = "gmail"
    scope_required = GMAIL_SCOPES

    def __init__(self, access_token: str, user_id: str, refresh_token: Optional[str] = None):
        """Initialize Gmail connector."""
        super().__init__(access_token, user_id)
        self.refresh_token = refresh_token
        self._service = None

    @property
    def service(self):
        """Get Gmail service."""
        if not self._service:
            # Create credentials object
            creds = Credentials(self.access_token, refresh_token=self.refresh_token)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    async def test_connection(self) -> bool:
        """Test Gmail connection."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            logger.info("Gmail connection test successful", email=profile.get("emailAddress"))
            return True
        except Exception as e:
            logger.error("Gmail connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get emails from Gmail."""
        try:
            # Build query
            query_parts = ['in:inbox', 'is:unread']  # Focus on unread messages

            if sync_cursor:
                # Use label history ID for incremental sync
                query_parts.append(f"after:{sync_cursor}")

            query = " ".join(query_parts)

            # Get message IDs
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=min(limit, 100),
                fields="messages,nextPageToken,resultSizeEstimate",
            ).execute()

            messages = results.get("messages", [])
            next_cursor = results.get("nextPageToken")

            # Fetch full message details
            emails = []
            for msg_id in messages:
                try:
                    msg = self.service.users().messages().get(
                        userId="me",
                        id=msg_id["id"],
                        format="full",
                    ).execute()
                    emails.append(msg)
                except Exception as e:
                    logger.warning("Failed to fetch email", email_id=msg_id["id"], error=str(e))
                    continue

            logger.info("Fetched emails from Gmail", count=len(emails))
            return emails, next_cursor

        except Exception as e:
            logger.error("Gmail fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Gmail email to unified work item."""
        try:
            headers = {h["name"]: h["value"] for h in item["payload"]["headers"]}
            subject = headers.get("Subject", "(No Subject)")
            from_addr = headers.get("From", "Unknown")
            timestamp = int(item["internalDate"]) // 1000
            received_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            # Extract body
            body = ""
            if "parts" in item["payload"]:
                for part in item["payload"]["parts"]:
                    if part["mimeType"] == "text/plain":
                        body = part["body"].get("data", "")
                        break
            else:
                body = item["payload"]["body"].get("data", "")

            # Create unified work item
            work_item = UnifiedWorkItem(
                source="gmail",
                source_id=item["id"],
                title=subject,
                description=body[:500] if body else None,  # Truncate
                created_by=from_addr,
                requires_response=True,  # Emails typically require response
                confidence_score=0.9,
                category="email",
                metadata={
                    "thread_id": item.get("threadId"),
                    "labels": item.get("labelIds", []),
                    "from": from_addr,
                    "received_time": received_date.isoformat(),
                },
            )

            return work_item.to_dict()

        except Exception as e:
            logger.error("Email normalization failed", error=str(e))
            raise


class GmailConnectorFactory:
    """Factory for creating Gmail connectors."""

    @staticmethod
    def create_from_oauth(access_token: str, user_id: str, refresh_token: Optional[str] = None) -> GmailConnector:
        """Create connector from OAuth tokens."""
        return GmailConnector(access_token, user_id, refresh_token)
