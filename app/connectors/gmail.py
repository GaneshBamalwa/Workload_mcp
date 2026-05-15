"""Gmail connector for email ingestion.

NOTE: google-api-python-client is synchronous. All API calls are wrapped
in asyncio.to_thread() so they don't block the MCP event loop.

Authentication: Requires GOOGLE_ACCESS_TOKEN (and GOOGLE_REFRESH_TOKEN for
auto-refresh). Run `python scripts/get_google_token.py` once to set these up.
"""
import asyncio
import base64
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

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

    def _get_creds(self) -> Credentials:
        """Build and (if needed) refresh Google credentials."""
        from app.core.config import settings

        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=GMAIL_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Persist new token back so subsequent calls work
            self.access_token = creds.token
        return creds

    def _build_service(self):
        creds = self._get_creds()
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    async def test_connection(self) -> bool:
        """Test Gmail connection."""
        try:
            svc = await asyncio.to_thread(self._build_service)
            profile = await asyncio.to_thread(
                lambda: svc.users().getProfile(userId="me").execute()
            )
            logger.info("Gmail connection test successful", email=profile.get("emailAddress"))
            return True
        except Exception as e:
            logger.error("Gmail connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get unread emails from Gmail inbox."""
        try:
            svc = await asyncio.to_thread(self._build_service)

            query_parts = ["in:inbox", "is:unread"]
            if sync_cursor:
                query_parts.append(f"after:{sync_cursor}")
            query = " ".join(query_parts)

            # List message IDs
            list_result = await asyncio.to_thread(
                lambda: svc.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(limit, 50),
                ).execute()
            )

            msg_refs: list[dict] = list_result.get("messages", [])
            next_cursor = list_result.get("nextPageToken")

            # Fetch full messages in parallel (up to 10 at a time to avoid rate limits)
            emails: list[dict] = []

            async def _fetch_msg(msg_id: str) -> Optional[dict]:
                try:
                    return await asyncio.to_thread(
                        lambda: svc.users().messages().get(
                            userId="me",
                            id=msg_id,
                            format="metadata",
                            metadataHeaders=["Subject", "From", "Date"],
                        ).execute()
                    )
                except Exception as e:
                    logger.warning("Failed to fetch email", email_id=msg_id, error=str(e))
                    return None

            # Batch requests (chunks of 10)
            chunk_size = 10
            for i in range(0, len(msg_refs), chunk_size):
                chunk = msg_refs[i : i + chunk_size]
                results = await asyncio.gather(*[_fetch_msg(m["id"]) for m in chunk])
                emails.extend(r for r in results if r is not None)

            logger.info("Fetched emails from Gmail", count=len(emails))
            return emails, next_cursor

        except Exception as e:
            logger.error("Gmail fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Gmail email to unified work item."""
        try:
            headers = {
                h["name"]: h["value"]
                for h in item.get("payload", {}).get("headers", [])
            }
            subject = headers.get("Subject", "(No Subject)")
            from_addr = headers.get("From", "Unknown")
            date_str = headers.get("Date", "")

            # Parse date
            received_date = None
            if item.get("internalDate"):
                ts = int(item["internalDate"]) // 1000
                received_date = datetime.fromtimestamp(ts, tz=timezone.utc)

            # Emails are inherently urgent — unread + in inbox
            work_item = UnifiedWorkItem(
                source="gmail",
                source_id=item["id"],
                title=f"[Email] {subject}",
                description=f"From: {from_addr}",
                created_by=from_addr,
                requires_response=True,
                urgency=0.65,
                importance=0.7,
                confidence_score=0.9,
                category="email",
                due_date=received_date,
                metadata={
                    "thread_id": item.get("threadId"),
                    "labels": item.get("labelIds", []),
                    "from": from_addr,
                    "subject": subject,
                    "received": received_date.isoformat() if received_date else None,
                    "snippet": item.get("snippet", "")[:200],
                },
            )
            return work_item.to_dict()

        except Exception as e:
            logger.error("Email normalization failed", error=str(e))
            raise


class GmailConnectorFactory:
    """Factory for creating Gmail connectors."""

    @staticmethod
    def create_from_oauth(
        access_token: str, user_id: str, refresh_token: Optional[str] = None
    ) -> GmailConnector:
        return GmailConnector(access_token, user_id, refresh_token)
