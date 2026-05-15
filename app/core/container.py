"""
Dependency injection container for managing application services.
Uses factory pattern for clean, testable architecture.
"""
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = structlog.get_logger(__name__)


class Container:
    """Application dependency injection container."""

    _engine = None
    _async_session_maker = None

    @classmethod
    async def initialize(cls) -> None:
        """Initialize all dependencies."""
        logger.info("Initializing dependency container...")

        # Create async engine
        cls._engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DATABASE_ECHO,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
        )

        # Create async session maker
        cls._async_session_maker = sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info("Dependency container initialized successfully")

    @classmethod
    async def shutdown(cls) -> None:
        """Shutdown all dependencies."""
        logger.info("Shutting down dependency container...")
        if cls._engine:
            await cls._engine.dispose()
        logger.info("Dependency container shutdown complete")

    @classmethod
    async def get_db_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """Get database session."""
        if not cls._async_session_maker:
            raise RuntimeError("Container not initialized. Call initialize() first.")

        async with cls._async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Database session error", error=str(e))
                raise
            finally:
                await session.close()

    @classmethod
    async def get_engine(self):
        """Get database engine."""
        if not self._engine:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._engine
