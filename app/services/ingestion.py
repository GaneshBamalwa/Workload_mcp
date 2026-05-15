"""Ingestion service for syncing data from connectors."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.calendar import CalendarConnector
from app.connectors.gmail import GmailConnector
from app.connectors.jira import JiraConnector
from app.connectors.slack import SlackConnector
from app.core.exceptions import SyncError
from app.db.repositories import IntegrationRepository, SyncStateRepository, WorkItemRepository
from app.models.base import Integration, SyncState, WorkItem

logger = structlog.get_logger(__name__)


class IngestionService:
    """Orchestrate ingestion from all connectors."""

    def __init__(self, session: AsyncSession):
        """Initialize ingestion service."""
        self.session = session
        self.work_item_repo = WorkItemRepository(WorkItem, session)
        self.integration_repo = IntegrationRepository(Integration, session)
        self.sync_state_repo = SyncStateRepository(SyncState, session)

    async def sync_user_sources(
        self,
        user_id: str,
        connectors_to_sync: Optional[list[str]] = None,
    ) -> dict[str, int]:
        """Sync all data sources for user.

        Returns:
            Dictionary of connector_type -> items_synced
        """
        logger.info("Starting user sync", user_id=user_id)
        results = {}

        # Get active integrations
        integrations = await self.integration_repo.get_active_by_user(user_id)

        for integration in integrations:
            connector_type = integration.connector_type

            # Skip if not in sync list
            if connectors_to_sync and connector_type not in connectors_to_sync:
                continue

            try:
                items_synced = await self._sync_connector(user_id, integration)
                results[connector_type] = items_synced
            except Exception as e:
                logger.error(
                    "Connector sync failed",
                    user_id=user_id,
                    connector=connector_type,
                    error=str(e),
                )
                # Update integration error count
                await self.integration_repo.update(
                    integration.id,
                    error_count=integration.error_count + 1,
                    last_error=str(e),
                )
                results[connector_type] = 0

        logger.info("User sync completed", user_id=user_id, results=results)
        return results

    async def _sync_connector(
        self,
        user_id: str,
        integration: Integration,
    ) -> int:
        """Sync single connector.

        Returns:
            Number of items synced
        """
        connector_type = integration.connector_type
        logger.info(
            "Syncing connector",
            user_id=user_id,
            connector=connector_type,
        )

        # Get sync state
        sync_state = await self.sync_state_repo.get_by_user_and_connector(
            user_id, connector_type
        )

        if not sync_state:
            sync_state = await self.sync_state_repo.create(
                id=str(uuid4()),
                user_id=user_id,
                connector_type=connector_type,
                status="idle",
            )

        try:
            # Update sync state to syncing
            await self.sync_state_repo.update(
                sync_state.id,
                status="syncing",
            )

            # Get connector instance
            connector = await self._get_connector(user_id, integration)
            if not connector:
                raise SyncError(f"Failed to initialize {connector_type} connector")

            # Fetch and normalize items
            sync_cursor = sync_state.sync_cursor
            items, next_cursor = await connector.get_normalized_items(
                sync_cursor=sync_cursor,
                limit=100,
            )

            # Store work items
            items_stored = 0
            for item in items:
                try:
                    # Check for duplicates
                    existing = await self.work_item_repo.get_by_source_id(
                        user_id, connector_type, item["source_id"]
                    )

                    if existing:
                        # Update existing
                        await self.work_item_repo.update(
                            existing.id,
                            **{k: v for k, v in item.items() if k != "source_id"},
                            updated_at=datetime.now(timezone.utc),
                        )
                    else:
                        # Create new
                        await self.work_item_repo.create(
                            id=str(uuid4()),
                            user_id=user_id,
                            **item,
                        )

                    items_stored += 1

                except Exception as e:
                    logger.warning(
                        "Failed to store work item",
                        connector=connector_type,
                        source_id=item.get("source_id"),
                        error=str(e),
                    )
                    continue

            # Update sync state
            await self.sync_state_repo.update(
                sync_state.id,
                status="idle",
                last_incremental_sync=datetime.now(timezone.utc),
                sync_cursor=next_cursor,
                error_count=0,
                last_error=None,
            )

            # Update integration
            await self.integration_repo.update(
                integration.id,
                last_synced_at=datetime.now(timezone.utc),
                error_count=0,
                last_error=None,
            )

            logger.info(
                "Connector sync completed",
                user_id=user_id,
                connector=connector_type,
                items_stored=items_stored,
            )

            return items_stored

        except Exception as e:
            # Update sync state with error
            await self.sync_state_repo.update(
                sync_state.id,
                status="error",
                error_count=sync_state.error_count + 1,
                last_error=str(e),
            )
            raise

    async def _get_connector(self, user_id: str, integration: Integration):
        """Get connector instance for integration."""
        connector_type = integration.connector_type

        try:
            if connector_type == "gmail":
                # Get Gmail tokens
                tokens = await self._get_oauth_tokens(user_id, "gmail")
                return GmailConnector(
                    tokens["access_token"],
                    user_id,
                    tokens.get("refresh_token"),
                )

            elif connector_type == "slack":
                tokens = await self._get_oauth_tokens(user_id, "slack")
                return SlackConnector(tokens["access_token"], user_id)

            elif connector_type == "calendar":
                tokens = await self._get_oauth_tokens(user_id, "calendar")
                return CalendarConnector(
                    tokens["access_token"],
                    user_id,
                    tokens.get("refresh_token"),
                )

            elif connector_type == "jira":
                # Jira uses API token auth
                settings = integration.settings
                return JiraConnector(
                    settings.get("jira_url"),
                    settings.get("user_email"),
                    settings.get("api_token"),
                )

            else:
                raise SyncError(f"Unknown connector type: {connector_type}")

        except Exception as e:
            logger.error(
                "Failed to get connector",
                connector=connector_type,
                error=str(e),
            )
            return None

    async def _get_oauth_tokens(self, user_id: str, connector_type: str) -> dict:
        """Get OAuth tokens for user."""
        # This would fetch from Token table and decrypt
        # Placeholder for now
        raise NotImplementedError("Token retrieval not yet implemented")


class SyncStateRepository:
    """Repository for sync state."""

    async def get_by_user_and_connector(
        self,
        user_id: str,
        connector_type: str,
    ) -> Optional[SyncState]:
        """Get sync state by user and connector."""
        # Placeholder - would query database
        return None

    async def create(self, **kwargs) -> SyncState:
        """Create sync state."""
        return SyncState(**kwargs)

    async def update(self, id_: str, **kwargs) -> SyncState:
        """Update sync state."""
        # Placeholder
        return SyncState()
