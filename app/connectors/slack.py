"""Slack connector for message ingestion.

NOTE: slack_sdk WebClient is synchronous. All API calls are wrapped in
asyncio.to_thread() so they don't block the MCP event loop.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.connectors.base import BaseConnector, UnifiedWorkItem

logger = structlog.get_logger(__name__)

# Bot token scopes required:
#   channels:read      – list channels the bot is in
#   channels:history   – read messages from public channels
#   groups:read        – private channels
#   groups:history     – read private channel messages
#   im:history         – DMs
#   users:read         – resolve user names
SLACK_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:history",
    "users:read",
]


class SlackConnector(BaseConnector):
    """Slack connector for message ingestion."""

    connector_type = "slack"
    scope_required = SLACK_SCOPES

    def __init__(self, access_token: str, user_id: str):
        """Initialize Slack connector."""
        super().__init__(access_token, user_id)
        # WebClient is sync – we'll call it via asyncio.to_thread()
        self.client = WebClient(token=access_token)

    async def test_connection(self) -> bool:
        """Test Slack connection."""
        try:
            resp = await asyncio.to_thread(self.client.auth_test)
            logger.info("Slack connection test successful", user_id=resp.get("user_id"), team=resp.get("team"))
            return True
        except SlackApiError as e:
            logger.error("Slack connection test failed", error=str(e))
            return False

    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get recent messages from Slack channels & DMs."""
        try:
            # --- List channels the bot has joined ---
            channels_resp = await asyncio.to_thread(
                self.client.conversations_list,
                types="public_channel,private_channel,im",
                limit=200,
            )
            channels: list[dict] = channels_resp.get("channels", [])

            if not channels:
                logger.warning("Slack: no channels accessible by this bot token")
                return [], None

            messages: list[dict] = []
            per_channel = max(1, limit // max(len(channels), 1))

            for channel in channels:
                channel_id: str = channel["id"]
                channel_name: str = channel.get("name", channel_id)

                kwargs: dict[str, Any] = {
                    "channel": channel_id,
                    "limit": min(per_channel, 20),
                }
                if sync_cursor:
                    kwargs["oldest"] = sync_cursor

                try:
                    hist = await asyncio.to_thread(
                        self.client.conversations_history, **kwargs
                    )
                    for msg in hist.get("messages", []):
                        # Skip bot messages / join/leave noise
                        if msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                            continue
                        # Only include messages with real text
                        if not msg.get("text", "").strip():
                            continue
                        msg["channel_id"] = channel_id
                        msg["channel_name"] = channel_name
                        messages.append(msg)
                except SlackApiError as e:
                    logger.warning(
                        "Failed to fetch channel history",
                        channel=channel_name,
                        error=str(e.response.get("error", str(e))),
                    )
                    continue

            # Sort by timestamp descending – newest first
            messages.sort(key=lambda m: float(m.get("ts", 0)), reverse=True)
            messages = messages[:limit]

            next_cursor = messages[-1].get("ts") if messages else None
            logger.info("Fetched messages from Slack", count=len(messages))
            return messages, next_cursor

        except SlackApiError as e:
            logger.error("Slack fetch failed", error=str(e.response.get("error", str(e))))
            raise

    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize Slack message to unified work item."""
        text: str = item.get("text", "")
        user_id: str = item.get("user", "unknown")
        channel_id: str = item.get("channel_id", "")
        channel_name: str = item.get("channel_name", "")
        timestamp = float(item.get("ts", 0))
        msg_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        # A message needs a response if: mentions the bot, is a DM, or has replies
        requires_response = (
            "<@" in text
            or channel_id.startswith("D")  # Direct message
            or item.get("reply_count", 0) > 0
        )

        # Resolve user name without making an extra API call per message
        created_by = user_id
        try:
            user_resp = await asyncio.to_thread(self.client.users_info, user=user_id)
            profile = user_resp["user"]["profile"]
            created_by = profile.get("real_name") or profile.get("email") or user_id
        except SlackApiError:
            pass

        work_item = UnifiedWorkItem(
            source="slack",
            source_id=f"{channel_id}:{item.get('ts')}",
            title=f"[Slack #{channel_name}] {text[:80]}",
            description=text,
            created_by=created_by,
            requires_response=requires_response,
            urgency=0.7 if requires_response else 0.4,
            importance=0.6,
            confidence_score=0.85,
            category="dm" if channel_id.startswith("D") else ("mention" if "<@" in text else "message"),
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


class SlackConnectorFactory:
    """Factory for creating Slack connectors."""

    @staticmethod
    def create_from_oauth(access_token: str, user_id: str) -> "SlackConnector":
        """Create connector from OAuth token."""
        return SlackConnector(access_token, user_id)
