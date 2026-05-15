"""Slack connector for message ingestion."""
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Slack scopes
SLACK_SCOPES = [
    "channels:read",
    "users:read",
    "chat:read",
    "emoji:read",
    "reactions:read",
]


class SlackConnector(BaseConnector):
    """Slack connector for message ingestion."""

    connector_type = "slack"
    scope_required = SLACK_SCOPES

    def __init__(self, access_token: str, user_id: str):
        """Initialize Slack connector."""
        super().__init__(access_token, user_id)
        self.client = WebClient(token=access_token)

    async def test_connection(self) -> bool:
        """Test Slack connection."""
        try:
            user_info = self.client.auth_test()
            logger.info(
                "Slack connection test successful",
                user_id=user_info["user_id"],
            )
            return True
        except SlackApiError as e:
            logger.error("Slack connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get messages from Slack channels."""
        try:
            # Get list of channels
            channels_response = self.client.conversations_list(
                types="public_channel,private_channel,im",
                limit=100,
            )
            channels = channels_response.get("channels", [])

            messages = []
            next_cursor = None

            # Get recent messages from each channel
            for channel in channels:
                try:
                    channel_id = channel["id"]
                    kwargs: dict[str, Any] = {
                        "channel": channel_id,
                        "limit": min(limit // len(channels) if channels else limit, 10),
                    }

                    if sync_cursor:
                        kwargs["oldest"] = sync_cursor

                    response = self.client.conversations_history(**kwargs)
                    channel_messages = response.get("messages", [])

                    for msg in channel_messages:
                        msg["channel_id"] = channel_id
                        msg["channel_name"] = channel.get("name", channel_id)
                        messages.append(msg)

                except SlackApiError as e:
                    logger.warning(
                        "Failed to fetch channel history",
                        channel_id=channel.get("id"),
                        error=str(e),
                    )
                    continue

            # Use latest message timestamp as cursor
            if messages:
                next_cursor = messages[-1].get("ts")

            logger.info("Fetched messages from Slack", count=len(messages))
            return messages, next_cursor

        except SlackApiError as e:
            logger.error("Slack fetch failed", error=str(e))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Slack message to unified work item."""
        try:
            # Extract message content
            text = item.get("text", "")
            user_id = item.get("user", "unknown")
            channel_id = item.get("channel_id", "")
            channel_name = item.get("channel_name", "")
            timestamp = float(item.get("ts", 0))
            msg_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            # Determine if message requires response
            # (mentions, replies, or direct messages)
            requires_response = (
                "<@" in text or
                item.get("type") == "message" and item.get("reply_count", 0) > 0 or
                channel_id.startswith("D")  # Direct message
            )

            # Get user info for created_by
            try:
                user_info = self.client.users_info(user=user_id)
                created_by = user_info["user"]["profile"]["email"]
            except SlackApiError:
                created_by = user_id

            # Create unified work item
            work_item = UnifiedWorkItem(
                source="slack",
                source_id=f"{channel_id}:{item.get('ts')}",
                title=f"Slack: {channel_name} - {text[:50]}",
                description=text,
                created_by=created_by,
                requires_response=requires_response,
                confidence_score=0.85,
                category="message" if not requires_response else "response_needed",
                metadata={
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "user_id": user_id,
                    "timestamp": msg_time.isoformat(),
                    "thread_ts": item.get("thread_ts"),
                    "reply_count": item.get("reply_count", 0),
                    "reactions": item.get("reactions", []),
                },
            )

            return work_item.to_dict()

        except Exception as e:
            logger.error("Slack message normalization failed", error=str(e))
            raise


class SlackConnectorFactory:
    """Factory for creating Slack connectors."""

    @staticmethod
    def create_from_oauth(access_token: str, user_id: str) -> SlackConnector:
        """Create connector from OAuth token."""
        return SlackConnector(access_token, user_id)
