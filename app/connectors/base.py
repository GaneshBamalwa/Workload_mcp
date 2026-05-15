"""Base connector class and interface."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class BaseConnector(ABC):
    """Abstract base class for external connectors."""

    connector_type: str  # Must be set by subclasses
    scope_required: list[str] = []

    def __init__(self, access_token: str, user_id: str):
        """Initialize connector."""
        self.access_token = access_token
        self.user_id = user_id
        logger.debug(
            "Connector initialized",
            connector=self.connector_type,
            user_id=user_id,
        )

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connector connection."""
        pass

    @abstractmethod
    async def get_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get items from connector.

        Returns:
            Tuple of (items, next_cursor)
        """
        pass

    @abstractmethod
    async def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize item to unified schema."""
        pass

    async def get_normalized_items(
        self,
        sync_cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Get and normalize items."""
        try:
            items, next_cursor = await self.get_items(sync_cursor, limit)
            normalized = []
            for item in items:
                try:
                    normalized_item = await self.normalize_item(item)
                    normalized.append(normalized_item)
                except Exception as e:
                    logger.warning(
                        "Failed to normalize item",
                        connector=self.connector_type,
                        error=str(e),
                    )
                    continue
            logger.info(
                "Items normalized",
                connector=self.connector_type,
                count=len(normalized),
            )
            return normalized, next_cursor
        except Exception as e:
            logger.error(
                "Connector error during normalization",
                connector=self.connector_type,
                error=str(e),
            )
            raise


class UnifiedWorkItem:
    """Unified work item schema from any source."""

    def __init__(
        self,
        source: str,
        source_id: str,
        title: str,
        description: Optional[str] = None,
        urgency: float = 0.5,
        importance: float = 0.5,
        estimated_effort_minutes: Optional[int] = None,
        due_date: Optional[datetime] = None,
        created_by: Optional[str] = None,
        stakeholders: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        requires_response: bool = False,
        requires_deep_work: bool = False,
        confidence_score: float = 0.7,
        category: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """Initialize unified work item."""
        self.source = source
        self.source_id = source_id
        self.title = title
        self.description = description
        self.urgency = max(0.0, min(1.0, urgency))
        self.importance = max(0.0, min(1.0, importance))
        self.estimated_effort_minutes = estimated_effort_minutes
        self.due_date = due_date
        self.created_by = created_by
        self.stakeholders = stakeholders or []
        self.dependencies = dependencies or []
        self.requires_response = requires_response
        self.requires_deep_work = requires_deep_work
        self.confidence_score = max(0.0, min(1.0, confidence_score))
        self.category = category
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "description": self.description,
            "urgency": self.urgency,
            "importance": self.importance,
            "estimated_effort_minutes": self.estimated_effort_minutes,
            "due_date": self.due_date,
            "created_by": self.created_by,
            "stakeholders": self.stakeholders,
            "dependencies": self.dependencies,
            "requires_response": self.requires_response,
            "requires_deep_work": self.requires_deep_work,
            "confidence_score": self.confidence_score,
            "category": self.category,
            "metadata": self.metadata,
        }
