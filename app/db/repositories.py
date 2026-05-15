"""Database repositories using repository pattern."""
from typing import Any, Generic, Optional, TypeVar

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")
logger = structlog.get_logger(__name__)


class BaseRepository(Generic[T]):
    """Generic base repository for database operations."""

    def __init__(self, model: type[T], session: AsyncSession):
        """Initialize repository."""
        self.model = model
        self.session = session

    async def create(self, **kwargs: Any) -> T:
        """Create new entity."""
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            logger.debug("Entity created", model=self.model.__name__, id=getattr(instance, "id", None))
            return instance
        except Exception as e:
            logger.error("Create failed", model=self.model.__name__, error=str(e))
            raise

    async def get_by_id(self, id_: str) -> Optional[T]:
        """Get entity by ID."""
        try:
            result = await self.session.execute(select(self.model).where(self.model.id == id_))
            return result.scalars().first()
        except Exception as e:
            logger.error("Get by ID failed", model=self.model.__name__, id=id_, error=str(e))
            return None

    async def list(self, skip: int = 0, limit: int = 100) -> list[T]:
        """List entities with pagination."""
        try:
            result = await self.session.execute(
                select(self.model).offset(skip).limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error("List failed", model=self.model.__name__, error=str(e))
            return []

    async def update(self, id_: str, **kwargs: Any) -> Optional[T]:
        """Update entity."""
        try:
            instance = await self.get_by_id(id_)
            if not instance:
                return None
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.flush()
            logger.debug("Entity updated", model=self.model.__name__, id=id_)
            return instance
        except Exception as e:
            logger.error("Update failed", model=self.model.__name__, id=id_, error=str(e))
            raise

    async def delete(self, id_: str) -> bool:
        """Delete entity."""
        try:
            instance = await self.get_by_id(id_)
            if not instance:
                return False
            await self.session.delete(instance)
            await self.session.flush()
            logger.debug("Entity deleted", model=self.model.__name__, id=id_)
            return True
        except Exception as e:
            logger.error("Delete failed", model=self.model.__name__, id=id_, error=str(e))
            raise

    async def exists(self, id_: str) -> bool:
        """Check if entity exists."""
        try:
            result = await self.session.execute(
                select(self.model).where(self.model.id == id_).limit(1)
            )
            return result.scalars().first() is not None
        except Exception as e:
            logger.error("Exists check failed", model=self.model.__name__, error=str(e))
            return False


class UserRepository(BaseRepository):
    """User-specific repository methods."""

    async def get_by_email(self, email: str) -> Optional[Any]:
        """Get user by email."""
        try:
            result = await self.session.execute(
                select(self.model).where(self.model.email == email)
            )
            return result.scalars().first()
        except Exception as e:
            logger.error("Get by email failed", email=email, error=str(e))
            return None

    async def get_by_username(self, username: str) -> Optional[Any]:
        """Get user by username."""
        try:
            result = await self.session.execute(
                select(self.model).where(self.model.username == username)
            )
            return result.scalars().first()
        except Exception as e:
            logger.error("Get by username failed", username=username, error=str(e))
            return None


class TokenRepository(BaseRepository):
    """Token-specific repository methods."""

    async def get_by_user_and_connector(self, user_id: str, connector_type: str) -> Optional[Any]:
        """Get token by user and connector type."""
        try:
            result = await self.session.execute(
                select(self.model).where(
                    (self.model.user_id == user_id) & (self.model.connector_type == connector_type)
                )
            )
            return result.scalars().first()
        except Exception as e:
            logger.error(
                "Get token failed",
                user_id=user_id,
                connector=connector_type,
                error=str(e),
            )
            return None

    async def get_valid_tokens(self, user_id: str) -> list[Any]:
        """Get all valid tokens for user."""
        try:
            result = await self.session.execute(
                select(self.model).where(
                    (self.model.user_id == user_id) & (self.model.is_valid == True)
                )
            )
            return result.scalars().all()
        except Exception as e:
            logger.error("Get valid tokens failed", user_id=user_id, error=str(e))
            return []


class WorkItemRepository(BaseRepository):
    """Work item-specific repository methods."""

    async def get_by_user_and_source(
        self, user_id: str, source: str, skip: int = 0, limit: int = 100
    ) -> list[Any]:
        """Get work items by user and source."""
        try:
            result = await self.session.execute(
                select(self.model)
                .where(
                    (self.model.user_id == user_id) & (self.model.source == source)
                )
                .offset(skip)
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(
                "Get work items by user and source failed",
                user_id=user_id,
                source=source,
                error=str(e),
            )
            return []

    async def get_pending_by_user(self, user_id: str) -> list[Any]:
        """Get pending work items for user."""
        try:
            result = await self.session.execute(
                select(self.model).where(
                    (self.model.user_id == user_id) & (self.model.status == "pending")
                )
            )
            return result.scalars().all()
        except Exception as e:
            logger.error("Get pending work items failed", user_id=user_id, error=str(e))
            return []


class IntegrationRepository(BaseRepository):
    """Integration-specific repository methods."""

    async def get_by_user_and_type(self, user_id: str, connector_type: str) -> Optional[Any]:
        """Get integration by user and type."""
        try:
            result = await self.session.execute(
                select(self.model).where(
                    (self.model.user_id == user_id) & (self.model.connector_type == connector_type)
                )
            )
            return result.scalars().first()
        except Exception as e:
            logger.error(
                "Get integration failed",
                user_id=user_id,
                connector=connector_type,
                error=str(e),
            )
            return None

    async def get_active_by_user(self, user_id: str) -> list[Any]:
        """Get active integrations for user."""
        try:
            result = await self.session.execute(
                select(self.model).where(
                    (self.model.user_id == user_id) & (self.model.is_active == True)
                )
            )
            return result.scalars().all()
        except Exception as e:
            logger.error("Get active integrations failed", user_id=user_id, error=str(e))
            return []
